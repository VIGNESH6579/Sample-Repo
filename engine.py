from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import requests

from simple_logic import Position, SimpleLogic
from tradingview_adapter import TradingViewScanner
from angelone_adapter import AngelOneProvider, angel_one_configured
from universe import load_universe

log = logging.getLogger("simple_logic")
IST = ZoneInfo("Asia/Kolkata")


class Monitor:
    def __init__(self):
        self.logic = SimpleLogic()
        self.provider = AngelOneProvider() if angel_one_configured() else TradingViewScanner()
        self.lock = threading.Lock()
        self.latest = {"status": "starting", "last_cycle": None, "candidate": [], "position": [], "message": None, "live_rows": 0}
        self.provider_status = self.provider.status() if hasattr(self.provider, "status") else {"provider": type(self.provider).__name__}
        self.positions: dict[str, Position] = {}
        self.trade_date: str | None = None
        self.start_sent_date: str | None = None
        self.eod_sent_date: str | None = None
        self.day_stats = {"entries": 0, "exits": 0, "entry_symbols": [], "exit_reasons": []}
        self.stop_event = threading.Event()
        self.universe = load_universe()
        self.symbols = [row["ticker"] for row in self.universe]
        self.ntfy_topic = os.getenv("NTFY_TOPIC", "simple_logic_alerts")
        self.ntfy_token = os.getenv("NTFY_TOKEN", "")

    def _notify(self, title: str, message: str, priority: str = "default", tags: str = "chart_with_upwards_trend") -> bool:
        if not self.ntfy_topic:
            log.error("ntfy notification skipped: NTFY_TOPIC is empty")
            return False
        headers = {"Title": title, "Priority": priority, "Tags": tags}
        if self.ntfy_token:
            headers["Authorization"] = f"Bearer {self.ntfy_token}"
        url = f"https://ntfy.sh/{self.ntfy_topic}"
        for attempt in range(3):
            try:
                response = requests.post(url, data=message.encode(), headers=headers, timeout=15)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "5")
                    try:
                        delay = min(max(float(retry_after), 1.0), 30.0)
                    except ValueError:
                        delay = 5.0
                    log.warning("ntfy rate limited title=%s attempt=%d retry_after=%.1fs", title, attempt + 1, delay)
                    if attempt < 2:
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                log.info("NTFY_SENT title=%s status=%d", title, response.status_code)
                return True
            except Exception:
                if attempt == 2:
                    log.exception("ntfy notification failed title=%s", title)
                else:
                    log.warning("ntfy notification attempt failed title=%s attempt=%d", title, attempt + 1)
        return False

    @staticmethod
    def _local_now() -> datetime:
        return datetime.now(IST)

    def _send_day_start(self, now: datetime):
        date_key = now.date().isoformat()
        if self.start_sent_date == date_key:
            return
        provider_name = getattr(self.provider, "name", "TradingView live scanner")
        sent = self._notify("Simple Logic DAY START", f"NSE F&O monitoring started\nDate: {date_key}\nTime: 09:15 IST\nStocks loaded: {len(self.symbols)}\nExcluded: LTIMindtree\nProvider: {provider_name}", "default", "sunrise,chart_with_upwards_trend")
        if sent:
            self.start_sent_date = date_key
            self.day_stats = {"entries": 0, "exits": 0, "entry_symbols": [], "exit_reasons": []}

    def _send_eod(self, now: datetime):
        date_key = now.date().isoformat()
        if self.eod_sent_date == date_key:
            return
        entries = ', '.join(self.day_stats["entry_symbols"]) or 'None'
        reasons = ', '.join(self.day_stats["exit_reasons"]) or 'None'
        sent = self._notify("Simple Logic EOD REPORT", f"NSE F&O monitoring ended\nDate: {date_key}\nTime: 15:40 IST\nEntry signals: {self.day_stats['entries']}\nEntry stocks: {entries}\nExits: {self.day_stats['exits']}\nExit reasons: {reasons}\nOpen positions: {len(self.positions)}\nUniverse: {len(self.symbols)} stocks; LTIM excluded", "default", "bar_chart")
        if sent:
            self.eod_sent_date = date_key

    def _in_market_hours(self, now: datetime) -> bool:
        t = now.astimezone(IST).time()
        return dt_time(9, 15) <= t <= dt_time(15, 35)

    def cycle(self):
        now = self._local_now()
        with self.lock:
            if self.trade_date != now.date().isoformat():
                self.trade_date = now.date().isoformat()
                self.start_sent_date = None
                self.eod_sent_date = None
            if now.time() >= dt_time(9, 15):
                self._send_day_start(now)
            if now.time() >= dt_time(15, 40):
                self._send_eod(now)
            self.latest["last_cycle"] = now.isoformat()
            self.latest["status"] = "market_closed" if not self._in_market_hours(now) else "scanning"
        if not self._in_market_hours(now):
            return

        snapshots = self.provider.snapshots(self.symbols)
        if hasattr(self.provider, "status"):
            self.provider_status = self.provider.status()
        log.info("DATA_CYCLE provider=%s live_rows=%d symbols=%d option_data_ready=%s ready=%s last_error=%s",
                 getattr(self.provider, "name", type(self.provider).__name__), len(snapshots), len(self.symbols),
                 self.provider_status.get("option_data_ready"), self.provider_status.get("ready"),
                 self.provider_status.get("last_error"))
        by_key = {f"{s.symbol}:{side}": s for s in snapshots for side in ("CALL", "PUT")}
        with self.lock:
            self.latest["live_rows"] = len(snapshots)
            if hasattr(self.provider, "status"):
                self.provider_status = self.provider.status()
            for key, position in list(self.positions.items()):
                current = by_key.get(key)
                if not current:
                    continue
                premium = current.atm_call_premium if position.side == "CALL" else current.atm_put_premium
                if premium is not None:
                    should, reason = self.logic.should_exit(position, premium, current.ltp, current.day_high, current.day_low, now)
                    if should:
                        self._notify("Simple Logic EXIT", f"SELL {position.side}\\nStock: {position.symbol}\\nEntry Premium: {position.entry_premium:.2f}\\nExit Premium: {premium:.2f}\\nReason: {reason}", "high", "warning,chart_with_downwards_trend")
                        self.latest["message"] = f"Exited {position.symbol} {position.side}: {reason}"
                        self.day_stats["exits"] += 1
                        self.day_stats["exit_reasons"].append(reason)
                        self.positions.pop(key, None)

            candidates = self.logic.candidates(snapshots, now)
            self.latest["candidate"] = [c.to_dict() for c in candidates]
            for candidate in candidates:
                key = f"{candidate.symbol}:{candidate.side}"
                if candidate.premium is None or key in self.positions:
                    continue
                position = Position(candidate.symbol, candidate.side, candidate.premium, candidate.spot, now)
                self.positions[key] = position
                self.day_stats["entries"] += 1
                self.day_stats["entry_symbols"].append(f"{candidate.symbol} {candidate.side}")
                self._notify("Simple Logic ENTRY", f"BUY ATM {candidate.side}\\nStock: {candidate.symbol}\\nSpot: {candidate.spot:.2f}\\nPremium: {candidate.premium:.2f}\\nScore: {candidate.score:.2f}", "high", "rocket,chart_with_upwards_trend")
                self.latest["message"] = f"Entered {candidate.symbol} {candidate.side}"
            self.latest["position"] = [p.__dict__ for p in self.positions.values()]

    def run(self):
        log.info("Simple Logic monitor started for %d live-mapped stocks; LTIM excluded", len(self.symbols))
        while not self.stop_event.is_set():
            try:
                self.cycle()
            except Exception:
                log.exception("MONITOR_CYCLE_FAILED")
                with self.lock:
                    self.latest["status"] = "error"
            self.stop_event.wait(60)

    def status(self):
        with self.lock:
            data = dict(self.latest)
            data["symbols"] = len(self.symbols)
            data["excluded"] = ["LTIM", "LTIMindtree"]
            data["provider"] = getattr(self.provider, "name", "TradingView live scanner")
            data["provider_status"] = dict(self.provider_status)
            data["trade_date"] = self.trade_date
            data["start_sent_date"] = self.start_sent_date
            data["eod_sent_date"] = self.eod_sent_date
            return data


monitor = Monitor()
