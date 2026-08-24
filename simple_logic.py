from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, time, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class MarketSnapshot:
    symbol: str
    ltp: float
    vwap: float
    day_high: float
    day_low: float
    volume: float
    average_volume: float
    call_oi_change_pct: Optional[float] = None
    put_oi_change_pct: Optional[float] = None
    call_spread: Optional[float] = None
    put_spread: Optional[float] = None
    atm_call_premium: Optional[float] = None
    atm_put_premium: Optional[float] = None
    timestamp: Optional[datetime] = None

    @property
    def volume_ratio(self) -> float:
        return self.volume / self.average_volume if self.average_volume else 0.0

    def score(self, side: str) -> float:
        oi = self.call_oi_change_pct if side == "CALL" else self.put_oi_change_pct
        return abs(oi or 0.0) + self.volume_ratio


@dataclass
class Candidate:
    symbol: str
    side: str
    score: float
    spot: float
    premium: Optional[float]
    timestamp: datetime
    reasons: list[str]

    def to_dict(self):
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class Position:
    symbol: str
    side: str
    entry_premium: float
    entry_spot: float
    entry_time: datetime


class SimpleLogic:
    excluded_symbols = {"LTIM", "LTIMINDTREE", "L&T INFOTECH"}

    def __init__(self, timezone=IST):
        self.timezone = timezone

    def is_excluded(self, symbol: str) -> bool:
        return symbol.strip().upper() in self.excluded_symbols

    def in_entry_window(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone).time()
        return time(9, 30) <= local <= time(15, 20)

    def diagnose(self, s: MarketSnapshot, side: str, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now(self.timezone)
        oi = s.call_oi_change_pct if side == "CALL" else s.put_oi_change_pct
        spread = s.call_spread if side == "CALL" else s.put_spread
        checks = {
            "entry_window": self.in_entry_window(now),
            "ltp_above_vwap" if side == "CALL" else "ltp_below_vwap": s.ltp > s.vwap if side == "CALL" else s.ltp < s.vwap,
            "at_current_session_high" if side == "CALL" else "at_current_session_low": s.ltp >= s.day_high if side == "CALL" else s.ltp <= s.day_low,
            "oi_change_below_-4pct": oi is not None and oi < -4,
            "spread_below_1_5": spread is not None and spread < 1.5,
            "volume_above_1_5x": s.volume_ratio > 1.5,
            "premium_available": (s.atm_call_premium if side == "CALL" else s.atm_put_premium) is not None,
        }
        return {"symbol": s.symbol, "side": side, "timestamp": (s.timestamp or now).isoformat(),
                "checks": checks, "failed": [k for k, v in checks.items() if not v],
                "ltp": s.ltp, "vwap": s.vwap, "day_high": s.day_high, "day_low": s.day_low,
                "volume_ratio": s.volume_ratio, "oi_change_pct": oi, "spread": spread,
                "premium": s.atm_call_premium if side == "CALL" else s.atm_put_premium}

    def candidates(self, snapshots: Iterable[MarketSnapshot], now: Optional[datetime] = None) -> list[Candidate]:
        now = now or datetime.now(self.timezone)
        out: list[Candidate] = []
        if not self.in_entry_window(now):
            return out
        for s in snapshots:
            if self.is_excluded(s.symbol) or s.volume_ratio <= 1.5:
                continue
            if (
                s.ltp > s.vwap and s.ltp >= s.day_high and
                (s.call_oi_change_pct is not None and s.call_oi_change_pct < -4) and
                (s.call_spread is not None and s.call_spread < 1.5)
            ):
                out.append(Candidate(s.symbol, "CALL", s.score("CALL"), s.ltp, s.atm_call_premium, now,
                                     ["LTP > VWAP", "LTP >= current-session Day High", "Call OI change < -4%", "Call spread < 1.5", "Volume > 1.5x average"]))
            if (
                s.ltp < s.vwap and s.ltp <= s.day_low and
                (s.put_oi_change_pct is not None and s.put_oi_change_pct < -4) and
                (s.put_spread is not None and s.put_spread < 1.5)
            ):
                out.append(Candidate(s.symbol, "PUT", s.score("PUT"), s.ltp, s.atm_put_premium, now,
                                     ["LTP < VWAP", "LTP <= current-session Day Low", "Put OI change < -4%", "Put spread < 1.5", "Volume > 1.5x average"]))
        return sorted(out, key=lambda c: c.score, reverse=True)

    def entry(self, snapshots: Iterable[MarketSnapshot], now: Optional[datetime] = None) -> Optional[Candidate]:
        candidates = self.candidates(snapshots, now)
        return candidates[0] if candidates else None

    def should_exit(self, position: Position, premium: float, spot: float, day_high: float, day_low: float,
                    now: Optional[datetime] = None) -> tuple[bool, str]:
        now = now or datetime.now(self.timezone)
        change = (premium - position.entry_premium) / position.entry_premium if position.entry_premium else 0.0
        if change >= 0.40:
            return True, "premium_target_+40%"
        if change <= -0.25:
            return True, "premium_stop_-25%"
        if now >= position.entry_time + timedelta(minutes=45):
            return True, "max_hold_45m"
        if position.side == "CALL" and spot < day_high:
            return True, "spot_below_day_high"
        if position.side == "PUT" and spot > day_low:
            return True, "spot_above_day_low"
        return False, ""


def snapshot_from_dict(row: dict) -> MarketSnapshot:
    return MarketSnapshot(**row)
