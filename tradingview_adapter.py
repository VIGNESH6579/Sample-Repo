from __future__ import annotations

import logging
import os
from typing import Iterable

import requests

from simple_logic import MarketSnapshot

log = logging.getLogger(__name__)


class TradingViewScanner:
    """Thin adapter around TradingView's public scanner endpoint.

    The endpoint and field names are configurable because availability varies by
    exchange/feed. The strategy engine only consumes normalized snapshots.
    """

    def __init__(self, timeout: int = 15):
        self.url = os.getenv("TRADINGVIEW_SCANNER_URL", "https://scanner.tradingview.com/india/scan")
        self.timeout = timeout

    def _scan(self, symbols: list[str], columns: list[str]) -> list[dict]:
        payload = {
            "symbols": {"tickers": [f"NSE:{s}" for s in symbols], "query": {"types": []}},
            "columns": columns,
            "options": {"lang": "en"},
        }
        response = requests.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("data", [])

    @staticmethod
    def _value(row: dict, name: str, columns: list[str]):
        values = row.get("d", [])
        try:
            return values[columns.index(name)]
        except (ValueError, IndexError):
            return row.get("s") if name == "name" else None

    def snapshots(self, symbols: Iterable[str]) -> list[MarketSnapshot]:
        symbols = [s for s in symbols if s]
        columns = [
            "name", "close", "high", "low", "VWAP", "volume",
            "average_volume_10d_calc", "open_interest", "change_in_open_interest",
            "bid", "ask", "call_oi_change_pct", "put_oi_change_pct",
            "call_spread", "put_spread", "atm_call_premium", "atm_put_premium",
        ]
        data = self._scan(symbols, columns)
        snapshots = []
        for row in data:
            def num(key):
                value = self._value(row, key, columns)
                try:
                    return float(value) if value is not None else None
                except (TypeError, ValueError):
                    return None

            symbol = self._value(row, "name", columns)
            values = {
                "symbol": symbol,
                "ltp": num("close"),
                "vwap": num("VWAP"),
                "day_high": num("high"),
                "day_low": num("low"),
                "volume": num("volume"),
                "average_volume": num("average_volume_10d_calc"),
                "call_oi_change_pct": num("call_oi_change_pct"),
                "put_oi_change_pct": num("put_oi_change_pct"),
                "call_spread": num("call_spread"),
                "put_spread": num("put_spread"),
                "atm_call_premium": num("atm_call_premium"),
                "atm_put_premium": num("atm_put_premium"),
            }
            if all(values.get(k) is not None for k in ("symbol", "ltp", "vwap", "day_high", "day_low", "volume", "average_volume")):
                snapshots.append(MarketSnapshot(**values))
        log.info("TradingView normalized %d/%d snapshots", len(snapshots), len(symbols))
        return snapshots
