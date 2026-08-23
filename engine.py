from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from simple_logic import Position, SimpleLogic
from tradingview_adapter import TradingViewScanner

log = logging.getLogger("simple_logic")
IST = ZoneInfo("Asia/Kolkata")


class Monitor:
    def __init__(self):
        self.logic = SimpleLogic()
        self.provider = TradingViewScanner()
        self.lock = threading.Lock()
        self.latest = {"status": "starting", "last_cycle": None, "candidate": [], "position": [], "message": None}
        self.positions: dict[str, Position] = {}
        self.alerted_setups: set[str] = set()
        self.trade_date: str | None = None
        self.stop_event = threading.Event()
        self.symbols = self._load_symbols()
        self.ntfy_topic = os.getenv("NTFY_TOPIC", "simple_logic_alerts")
        self.ntfy_token = os.getenv("NTFY_TOKEN", "")

    @staticmethod
    def _load_symbols() -> list[str]:
        from modules.nse_data import FO_STOCKS
        return [s for s in FO_STOCKS if s.upper() not in {"LTIM", "LTIMINDTREE"}]

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

    def _in_market_hours(self, now: datetime) -> bool:
        t = now.astimezone(IST).time()
        return dt_time(9, 15) <= t <= dt_time(15, 35)

    def cycle(self):
        now = datetime.now(IST)
        with self.lock:
            if self.trade_date != now.date().isoformat():
                self.trade_date = now.date().isoformat()
                self.alerted_setups.clear()
            self.latest["last_cycle"] = now.isoformat()
            self.latest["status"] = "market_closed" if not self._in_market_hours(now) else "scanning"
        if not self._in_market_hours(now):
            return

        snapshots = self.provider.snapshots(self.symbols)
        by_key = {f"{s.symbol}:{side}": s for s in snapshots for side in ("CALL", "PUT")}
        with self.lock:
            for key, position in list(self.positions.items()):
                current = by_key.get(key)
                if not current:
                    continue
                premium = current.atm_call_premium if position.side == "CALL" else current.atm_put_premium
                if premium is not None:
                    should, reason = self.logic.should_exit(position, premium, current.ltp, current.day_high, current.day_low, now)
                    if should:
                        self._notify("Simple Logic EXIT", f"SELL {position.side} {position.symbol}\nReason: {reason}\nPremium: {premium:.2f}", "high", "warning,chart_with_downwards_trend")
                        self.latest["message"] = f"Exited {position.symbol} {position.side}: {reason}"
                        self.positions.pop(key, None)
                        self.alerted_setups.discard(key)

            candidates = self.logic.candidates(snapshots, now)
            self.latest["candidate"] = [c.to_dict() for c in candidates]
            for candidate in candidates:
                key = f"{candidate.symbol}:{candidate.side}"
                if candidate.premium is None or key in self.positions:
                    continue
                position = Position(candidate.symbol, candidate.side, candidate.premium, candidate.spot, now)
                self.positions[key] = position
                self.alerted_setups.add(key)
                self._notify("Simple Logic ENTRY", f"BUY ATM {candidate.side}\nStock: {candidate.symbol}\nSpot: {candidate.spot:.2f}\nPremium: {candidate.premium:.2f}\nScore: {candidate.score:.2f}\nWindow: 09:30-11:30 IST", "high", "rocket,chart_with_upwards_trend")
                self.latest["message"] = f"Entered {candidate.symbol} {candidate.side}"
            self.latest["position"] = [p.__dict__ for p in self.positions.values()]

    def run(self):
        log.info("Simple Logic monitor started for %d symbols; LTIM excluded", len(self.symbols))
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
            data["provider"] = "TradingView scanner"
            data["trade_date"] = self.trade_date
            return data


monitor = Monitor()
