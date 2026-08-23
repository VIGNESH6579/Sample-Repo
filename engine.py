from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import requests

from simple_logic import Position, SimpleLogic
from tradingview_adapter import TradingViewScanner
from universe import load_universe

log = logging.getLogger("simple_logic")
IST = ZoneInfo("Asia/Kolkata")


class Monitor:
    def __init__(self):
        self.logic = SimpleLogic()
        self.provider = TradingViewScanner()
        self.lock = threading.Lock()
        self.latest = {"status": "starting", "last_cycle": None, "candidate": [], "position": [], "message": None, "live_rows": 0}
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

    def _notify(self, title: str, message: str, priority: str = "default", tags: str = "chart_with_upwards_trend"):
        if not self.ntfy_topic:
            return
        headers = {"Title": title, "Priority": priority, "Tags": tags}
        if self.ntfy_token:
            headers["Authorization"] = f"Bearer {self.ntfy_token}"
        try:
            response = requests.post(f"https://ntfy.sh/{self.ntfy_topic}", data=message.encode(), headers=headers, timeout=15)
            response.raise_for_status()
        except Exception:
            log.exception("ntfy notification failed")

    @staticmethod
    def _local_now() -> datetime:
        return datetime.now(IST)

    def _send_day_start(self, now: datetime):
        date_key = now.date().isoformat()
        if self.start_sent_date == date_key:
            return
        self.start_sent_date = date_key
        self.day_stats = {"entries": 0, "exits": 0, "entry_symbols": [], "exit_reasons": []}
        self._notify("Simple Logic DAY START", f"NSE F&O monitoring started\nDate: {date_key}\nTime: 09:15 IST\nStocks loaded: {len(self.symbols)}\nExcluded: LTIMindtree\nProvider: TradingView live scanner", "default", "sunrise,chart_with_upwards_trend")

    def _send_eod(self, now: datetime):
        date_key = now.date().isoformat()
        if self.eod_sent_date == date_key:
            return
        self.eod_sent_date = date_key
        entries = ', '.join(self.day_stats["entry_symbols"]) or 'None'
        reasons = ', '.join(self.day_stats["exit_reasons"]) or 'None'
        self._notify("Simple Logic EOD REPORT", f"NSE F&O monitoring ended\nDate: {date_key}\nTime: 15:40 IST\nEntry signals: {self.day_stats['entries']}\nEntry stocks: {entries}\nExits: {self.day_stats['exits']}\nExit reasons: {reasons}\nOpen positions: {len(self.positions)}\nUniverse: {len(self.symbols)} stocks; LTIM excluded", "default", "bar_chart")

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
        by_key = {f"{s.symbol}:{side}": s for s in snapshots for side in ("CALL", "PUT")}
        with self.lock:
            self.latest["live_rows"] = len(snapshots)
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
                log.exception("monitor cycle failed")
                with self.lock:
                    self.latest["status"] = "error"
            self.stop_event.wait(60)

    def status(self):
        with self.lock:
            data = dict(self.latest)
            data["symbols"] = len(self.symbols)
            data["excluded"] = ["LTIM", "LTIMindtree"]
            data["provider"] = "TradingView live scanner"
            data["trade_date"] = self.trade_date
            data["start_sent_date"] = self.start_sent_date
            data["eod_sent_date"] = self.eod_sent_date
            return data


monitor = Monitor()
