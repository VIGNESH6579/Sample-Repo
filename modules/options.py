"""
options.py — Option-chain analysis without a paid option-data feed.

Since live option premiums are not available free-of-cost programmatically,
this module computes everything the signal engine needs from the spot price
and intraday volatility:

  1. ATM strike selection (NSE convention: 10-rupee steps below 500,
     50 above, round-to-nearest ATM logic)
  2. Synthetic ATM premium via Black-Scholes with IV proxied by
     realized (historical) intraday volatility — a standard free-system
     approximation used widely in algo trading research
  3. Expected option move per underlying move (delta proxy) for P&L sizing
  4. IV-percentile context: compares short-term RV vs 20-day RV

All of this is exactly what the backtest and live signal engine consume.
"""
import math
import logging
import numpy as np
import pandas as pd

log = logging.getLogger("nse_scalper.options")

RISK_FREE = 0.065  # ~current Indian risk-free rate


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_price(s: float, k: float, t: float, sigma: float, r: float = RISK_FREE,
             option_type: str = "call") -> float:
    """Black-Scholes European price. t in years, sigma annualized."""
    if t <= 0 or sigma <= 0 or s <= 0 or k <= 0:
        return 0.0
    d1 = (math.log(s / k) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if option_type == "call":
        return s * norm_cdf(d1) - k * math.exp(-r * t) * norm_cdf(d2)
    return k * math.exp(-r * t) * norm_cdf(-d2) - s * norm_cdf(-d1)


def bs_delta(s: float, k: float, t: float, sigma: float, option_type: str = "call") -> float:
    if t <= 0 or sigma <= 0 or s <= 0:
        return 0.0
    d1 = (math.log(s / k) + (RISK_FREE + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    return norm_cdf(d1) if option_type == "call" else norm_cdf(d1) - 1


def atm_strike(spot: float) -> float:
    """NSE stock option strike step: 10 below 5000, 50 above (approx convention)."""
    if spot < 500:
        step = 10
    elif spot < 5000:
        step = 50
    else:
        step = 100
    raw = round(spot / step) * step
    up = raw + step
    return raw if abs(raw - spot) <= abs(up - spot) else up


def realized_vol(bars: pd.DataFrame, window: int, annualize: float = None) -> float:
    """Annualized realized vol from close-to-close returns of intraday bars."""
    if len(bars) < window + 2:
        return np.nan
    ret = bars["close"].pct_change().dropna()
    sigma_d = ret.iloc[-window:].std()
    if annualize is None:
        # intraday bars: 5m -> 78 bars/day -> 252 days/year
        minutes = (bars.index[-1] - bars.index[-2]).total_seconds() / 60
        bars_per_day = 390 / minutes
        annualize = math.sqrt(bars_per_day * 252)
    return sigma_d * annualize


def synthetic_atm_premium(spot: float, bars_5m: pd.DataFrame,
                          days_to_expiry: float = 15.0,
                          option_type: str = "call") -> dict:
    """Compute ATM strike, premium, delta, and vol context for a stock.

    days_to_expiry: use next weekly expiry. For monthly use ~20.
    Returns dict or empty dict on failure.
    """
    if len(bars_5m) < 60:
        return {}
    k = atm_strike(spot)
    # short-term vol: last 2 days (~156 5m bars); context: last 20 sessions
    short = bars_5m.iloc[-160:] if len(bars_5m) >= 160 else bars_5m
    long_ctx = bars_5m.iloc[-(160 * 10):] if len(bars_5m) >= 1600 else bars_5m
    sig_short = realized_vol(short, min(150, len(short) - 2))
    sig_long = realized_vol(long_ctx, min(1500, len(long_ctx) - 2))
    if np.isnan(sig_short) or sig_short <= 0:
        return {}
    # vol mean-reversion context: scale IV slightly toward longer-term RV
    iv = 0.6 * sig_short + 0.4 * sig_long if not np.isnan(sig_long) else sig_short
    t = max(days_to_expiry / 365, 1 / 365)
    premium = bs_price(spot, k, t, iv, option_type=option_type)
    delta = bs_delta(spot, k, t, iv, option_type=option_type)
    return {
        "spot": spot,
        "atm_strike": k,
        "iv_annual": round(iv, 4),
        "premium_synthetic": round(premium, 2),
        "delta": round(delta, 3),
        "rv_short": round(sig_short, 4),
        "rv_long": round(sig_long, 4) if not np.isnan(sig_long) else None,
        "vol_context": "elevated" if (not np.isnan(sig_long) and sig_short > 1.2 * sig_long) else "normal",
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")
    from modules.nse_data import get_intraday_bars
    logging.basicConfig(level=logging.INFO)
    bars = get_intraday_bars("RELIANCE", "5m", "5d")
    q_price = None
    from modules.nse_data import get_quote
    q = get_quote("RELIANCE")
    spot = q.get("price")
    print("spot:", spot)
    res = synthetic_atm_premium(spot, bars, days_to_expiry=15)
    print(res)
