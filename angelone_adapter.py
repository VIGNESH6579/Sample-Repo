"""Alert-only Angel One SmartAPI market-data provider.

No order-placement methods are imported or called. The adapter uses SmartAPI
login plus the full quote endpoint, an official instrument master, and live
NFO contracts selected by nearest expiry and ATM strike.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from statistics import mean
from typing import Iterable
from zoneinfo import ZoneInfo

import requests

from simple_logic import MarketSnapshot

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
ROOT = "https://apiconnect.angelone.in"
MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"


class AngelOneProvider:
    name = "Angel One SmartAPI"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.api_key = os.getenv("ANGEL_API_KEY", "")
        self.client_id = os.getenv("ANGEL_CLIENT_ID", "")
        self.password = os.getenv("ANGEL_PASSWORD", "")
        self.totp_secret = os.getenv("ANGEL_TOTP_SECRET", "")
        self.session = requests.Session()
        self.jwt: str | None = None
        self.last_error: str | None = None
        self.last_data_at: str | None = None
        self.instrument_rows: list[dict] = []
        self.equity_by_name: dict[str, dict] = {}
        self.options_by_name: dict[str, list[dict]] = {}
        self.previous_oi: dict[str, float] = {}
        self.session_oi: dict[str, float] = {}
        self.session_oi_date: str | None = None
        self.session_extrema: dict[str, tuple[float, float]] = {}
        self.session_extrema_date: str | None = None
        self.volume_baseline: dict[str, float] = {}
        self.volume_baseline_date: str | None = None
        self.ready = False

    def _headers(self, auth: bool = True) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json",
             "X-UserType": "USER", "X-SourceID": "WEB", "X-PrivateKey": self.api_key,
             "X-ClientLocalIP": os.getenv("ANGEL_CLIENT_LOCAL_IP", "127.0.0.1"),
             "X-ClientPublicIP": os.getenv("ANGEL_CLIENT_PUBLIC_IP", "127.0.0.1"),
             "X-MACAddress": os.getenv("ANGEL_MAC_ADDRESS", "00:00:00:00:00:00")}
        if auth and self.jwt:
            h["Authorization"] = f"Bearer {self.jwt}"
        return h

    def _configured(self) -> bool:
        return all((self.api_key, self.client_id, self.password, self.totp_secret))

    def connect(self) -> bool:
        if self.ready:
            return True
        if not self._configured():
            self.last_error = "Angel One credentials incomplete"
            return False
        try:
            import pyotp
            body = {"clientcode": self.client_id, "password": self.password,
                    "totp": pyotp.TOTP(self.totp_secret).now()}
            r = self.session.post(ROOT + "/rest/auth/angelbroking/user/v1/loginByPassword",
                                  json=body, headers=self._headers(False), timeout=self.timeout)
            data = r.json()
            if not data.get("status") or not data.get("data", {}).get("jwtToken"):
                self.last_error = "Angel One authentication rejected"
                return False
            self.jwt = data["data"]["jwtToken"]
            self._load_master()
            self.ready = True
            self.last_error = None
            return True
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            code = getattr(response, "status_code", "unknown")
            endpoint = getattr(response, "url", "unknown")
            self.last_error = f"Angel One HTTP {code} at {endpoint.rsplit('/', 1)[-1]}"
            log.error("Angel One HTTP failure status=%s endpoint=%s", code, endpoint)
            return False
        except Exception as exc:
            self.last_error = f"Angel One connection failed: {type(exc).__name__}"
            log.exception("Angel One connection failed")
            return False

    def _load_master(self) -> None:
        r = self.session.get(MASTER_URL, timeout=60)
        r.raise_for_status()
        rows = r.json()
        self.instrument_rows = rows
        self.equity_by_name = {}
        self.options_by_name = {}
        for row in rows:
            seg = row.get("exch_seg")
            name = str(row.get("name", "")).upper().strip()
            if seg == "NSE" and str(row.get("symbol", "")).endswith("-EQ"):
                self.equity_by_name.setdefault(name, row)
            elif seg == "NFO" and row.get("instrumenttype") in {"OPTSTK", "OPTIDX"}:
                self.options_by_name.setdefault(name, []).append(row)

    @staticmethod
    def _quote_payload(data: dict) -> list[dict]:
        return (data.get("data") or {}).get("fetched") or []

    def _historical_average_volume(self, token: str) -> float | None:
        today = datetime.now(IST).date()
        if self.volume_baseline_date != today.isoformat():
            self.volume_baseline.clear()
            self.volume_baseline_date = today.isoformat()
        if token in self.volume_baseline:
            return self.volume_baseline[token]
        to_date = datetime.now(IST).replace(hour=9, minute=15, second=0, microsecond=0)
        from_date = to_date - timedelta(days=45)
        body = {"exchange": "NSE", "symboltoken": str(token), "interval": "ONE_DAY",
                "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
                "todate": to_date.strftime("%Y-%m-%d %H:%M")}
        try:
            r = self.session.post(ROOT + "/rest/secure/angelbroking/historical/v1/getCandleData",
                                  json=body, headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            rows = (r.json().get("data") or [])
            volumes = [float(row[5]) for row in rows[-20:] if len(row) > 5 and self._num(row[5]) is not None]
            baseline = mean(volumes) if volumes else None
            if baseline is not None:
                self.volume_baseline[token] = baseline
            return baseline
        except Exception as exc:
            log.warning("historical volume unavailable token=%s error=%s", token, type(exc).__name__)
            return None

    def _volume_baselines(self, rows: dict[str, dict]) -> dict[str, float]:
        result: dict[str, float] = {}
        missing = [(symbol, row) for symbol, row in rows.items() if str(row.get("token")) not in self.volume_baseline]
        if missing:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(self._historical_average_volume, str(row["token"])): symbol for symbol, row in missing}
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        value = future.result()
                    except Exception:
                        value = None
                    if value is not None:
                        result[symbol] = value
        for symbol, row in rows.items():
            value = self.volume_baseline.get(str(row.get("token")))
            if value is not None:
                result[symbol] = value
        return result

    def _quotes(self, exchange: str, tokens: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for start in range(0, len(tokens), 50):
            chunk = tokens[start:start + 50]
            body = {"mode": "FULL", "exchangeTokens": {exchange: chunk}}
            r = self.session.post(ROOT + "/rest/secure/angelbroking/market/v1/quote/",
                                  json=body, headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            for q in self._quote_payload(r.json()):
                out[str(q.get("symbolToken"))] = q
            if start + 50 < len(tokens):
                time.sleep(1.05)
        return out

    @staticmethod
    def _num(value):
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _spread(q: dict) -> float | None:
        depth = q.get("depth") or {}
        buys, sells = depth.get("buy") or [], depth.get("sell") or []
        bid = AngelOneProvider._num(buys[0].get("price")) if buys else None
        ask = AngelOneProvider._num(sells[0].get("price")) if sells else None
        return ask - bid if bid is not None and ask is not None and ask >= bid else None

    def _atm_contract(self, symbol: str, spot: float, side: str) -> dict | None:
        rows = self.options_by_name.get(symbol.upper(), [])
        today = datetime.now(IST).date()
        candidates = []
        for row in rows:
            if row.get("symbol", "").upper().endswith("CE") != (side == "CALL"):
                continue
            try:
                expiry = datetime.strptime(str(row.get("expiry")), "%d%b%Y").date()
                strike = float(row.get("strike")) / 100
            except (TypeError, ValueError):
                continue
            if expiry >= today:
                candidates.append((expiry, abs(strike - spot), row))
        if not candidates:
            return None
        nearest_expiry = min(x[0] for x in candidates)
        same_expiry = [x for x in candidates if x[0] == nearest_expiry]
        return min(same_expiry, key=lambda x: x[1])[2]

    def snapshots(self, symbols: Iterable[str]) -> list[MarketSnapshot]:
        if not self.connect():
            return []
        symbols = [s.upper().strip() for s in symbols if s]
        today_key = datetime.now(IST).date().isoformat()
        if self.session_oi_date != today_key:
            self.session_oi.clear()
            self.session_oi_date = today_key
        if self.session_extrema_date != today_key:
            self.session_extrema.clear()
            self.session_extrema_date = today_key
        equities = {s: self.equity_by_name.get(s) for s in symbols}
        equities = {s: row for s, row in equities.items() if row}
        eq_quotes = self._quotes("NSE", [str(row["token"]) for row in equities.values()])
        options: dict[tuple[str, str], dict] = {}
        for symbol, row in equities.items():
            eq = eq_quotes.get(str(row["token"]))
            spot = self._num((eq or {}).get("ltp"))
            if spot is None:
                continue
            for side in ("CALL", "PUT"):
                contract = self._atm_contract(symbol, spot, side)
                if contract:
                    options[(symbol, side)] = contract
        opt_quotes = self._quotes("NFO", [str(row["token"]) for row in options.values()]) if options else {}
        volume_baselines = self._volume_baselines(equities)
        fetched_at = datetime.now(IST)
        out: list[MarketSnapshot] = []
        for symbol, row in equities.items():
            eq = eq_quotes.get(str(row["token"]))
            if not eq:
                continue
            spot = self._num(eq.get("ltp")); high = self._num(eq.get("high")); low = self._num(eq.get("low"))
            vwap = self._num(eq.get("avgPrice")); volume = self._num(eq.get("tradeVolume"))
            previous_extrema = self.session_extrema.get(symbol)
            high_touch_event = bool(previous_extrema and high > previous_extrema[0]) if high is not None else False
            low_touch_event = bool(previous_extrema and low < previous_extrema[1]) if low is not None else False
            if spot is not None and high is not None and spot >= high:
                high_touch_event = True
            if spot is not None and low is not None and spot <= low:
                low_touch_event = True
            if high is not None and low is not None:
                self.session_extrema[symbol] = (high, low)
            average = volume_baselines.get(symbol)
            if None in (spot, high, low, vwap, volume, average):
                continue
            cq, pq = opt_quotes.get(str((options.get((symbol, "CALL")) or {}).get("token"))), opt_quotes.get(str((options.get((symbol, "PUT")) or {}).get("token")))
            def oi_pair(q, key):
                oi = self._num((q or {}).get("opnInterest"))
                baseline = self.session_oi.get(key)
                if oi is not None and baseline is None:
                    self.session_oi[key] = oi
                    baseline = oi
                change = ((oi - baseline) / baseline * 100) if oi is not None and baseline not in (None, 0) else None
                if oi is not None: self.previous_oi[key] = oi
                return change
            call_change = oi_pair(cq, symbol + ":CALL")
            put_change = oi_pair(pq, symbol + ":PUT")
            out.append(MarketSnapshot(symbol=symbol, ltp=spot, vwap=vwap, day_high=high, day_low=low,
                volume=volume, average_volume=average, call_oi_change_pct=call_change,
                put_oi_change_pct=put_change, call_spread=self._spread(cq or {}),
                put_spread=self._spread(pq or {}), atm_call_premium=self._num((cq or {}).get("ltp")),
                atm_put_premium=self._num((pq or {}).get("ltp")), timestamp=fetched_at,
                high_touch_event=high_touch_event, low_touch_event=low_touch_event))
        self.last_data_at = fetched_at.isoformat()
        return out

    def status(self) -> dict:
        return {"provider": self.name, "credentials_configured": self._configured(),
                "ready": self.ready, "option_data_ready": bool(self.ready and self.options_by_name),
                "last_error": self.last_error, "last_data_at": self.last_data_at}


def angel_one_configured() -> bool:
    return all(os.getenv(name, "") for name in ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PASSWORD", "ANGEL_TOTP_SECRET"))
