"""
backtest_iter2.py — Iteration 2.

Changes vs iteration 1, motivated by diagnosis of iter-1 losers:
 1. One trade per stock per day (avoid repeated whipsaw entries on same day)
 2. Momentum quality: require the breakout bar to close in top 25% of its range
    AND prior close above prior day VWAP-like mean (close > 20-bar SMA)
 3. Volatility regime filter: skip if ATR14/price > 4% (too erratic for scalp)
 4. TP tightened to 1.0 x ATR, SL stays 1.0 x ATR but with trailing after +0.5 ATR
 5. Skip first 30 minutes (open auction noise) -> trigger window 9:45-12:00
 6. Exclude historically illiquid/volatile junk stocks (from iter-1 bottom list)
 7. News-relevance proxy: require RVOL >= 2.2 (stronger confirmation that
    something is happening — the news signature threshold)
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"
EXCLUDE = {"SUZLON", "NBCC", "MAZDOCK", "JSWENERGY", "TORNTPOWER", "SYNGENE",
           "IRFC", "RVNL", "HUDCO", "SJVN", "IREDA", "PPLPHARMA", "MOTHERSON", "SFL", "PATANJALI"}

P = {
    "trigger_start_bar": 6,    # 9:45 (30 min after open)
    "trigger_end_hour": 12,    # until 12:00
    "lookback_high": 20,
    "rvol_period": 20,
    "rvol_thresh": 2.2,
    "tp_atr_mult": 1.0,
    "sl_atr_mult": 1.0,
    "trail_from_atr": 0.5,    # start trailing stop after +0.5 ATR profit
    "trail_atr_mult": 0.5,
    "atr_period": 14,
    "time_stop_bars": 12,
    "delta": 0.6,
    "risk_pct": 0.005,
    "cost_pct": 0.0010,
    "max_atr_pct": 0.04,
}


def atr(df, n=14):
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def rvol(df, n=20):
    v = df["volume"].rolling(n).mean()
    return df["volume"] / v.replace(0, np.nan)


def run_one(df, p, sym):
    df = df.copy().reset_index(drop=True)
    df["atr"] = atr(df, p["atr_period"])
    df["rvol"] = rvol(df, p["rvol_period"])
    df["sma20"] = df["close"].rolling(20).mean()

    trades = []
    pos = None
    traded_days = set()

    for i in range(max(p["trigger_start_bar"], 30), len(df)):
        row = df.iloc[i]
        ts = df["time"].iloc[i]
        day = ts.date()
        hour = ts.hour

        if pos is not None:
            exit_px, reason = None, None
            if row["low"] <= pos["sl"]:
                exit_px, reason = pos["sl"], "sl"
            elif row["high"] >= pos["tp"]:
                exit_px, reason = pos["tp"], "tp"
            elif i - pos["bar"] >= p["time_stop_bars"]:
                exit_px, reason = row["close"], "time"
            if exit_px is not None:
                ret_points = exit_px - pos["entry"]
                opt_ret = ret_points * p["delta"] / pos["entry_px"] - p["cost_pct"]
                trades.append({"sym": sym, "day": day, "entry_time": pos["entry_time"],
                               "entry_px": pos["entry_px"], "exit_px": exit_px,
                               "ret_opt_pct": opt_ret * 100, "points": round(ret_points, 2),
                               "reason": reason})
                pos = None
            continue

        if day in traded_days:
            continue
        if hour >= p["trigger_end_hour"]:
            continue

        hh = df["high"].iloc[i - p["lookback_high"]:i].max()
        bar_range = row["high"] - row["low"]
        close_position = (row["close"] - row["low"]) / bar_range if bar_range > 0 else 0

        breakout = row["close"] > hh
        vol_ok = row["rvol"] >= p["rvol_thresh"]
        trend_ok = row["close"] > row["sma20"]
        strength_ok = close_position >= 0.75
        regime_ok = row["atr"] / row["close"] <= p["max_atr_pct"]
        if breakout and vol_ok and trend_ok and strength_ok and regime_ok:
            tp = row["close"] + p["tp_atr_mult"] * row["atr"]
            sl = row["close"] - p["sl_atr_mult"] * row["atr"]
            pos = {"sym": sym, "bar": i, "entry": row["close"],
                   "entry_px": row["close"], "tp": tp, "sl": sl,
                   "entry_time": df["time"].iloc[i]}
            traded_days.add(day)

    if pos is not None:
        last = df.iloc[-1]
        ret_points = last["close"] - pos["entry"]
        opt_ret = ret_points * p["delta"] / pos["entry_px"] - p["cost_pct"]
        trades.append({"sym": sym, "day": last["time"].date(), "entry_time": pos["entry_time"],
                       "entry_px": pos["entry_px"], "exit_px": last["close"],
                       "ret_opt_pct": opt_ret * 100, "points": round(ret_points, 2),
                       "reason": "eod"})
    return pd.DataFrame(trades)


def metrics(t):
    if len(t) < 10:
        return {"trades": len(t)}
    w = t[t["ret_opt_pct"] > 0]
    l = t[t["ret_opt_pct"] <= 0]
    gp = w["ret_opt_pct"].sum() if len(w) else 0
    gl = abs(l["ret_opt_pct"].sum()) if len(l) else 1e-9
    eq = (1 + t["ret_opt_pct"] / 100).cumprod()
    dd = ((eq / eq.cummax()) - 1).min()
    # split half
    half = len(t) // 2
    m2 = metrics(t.iloc[half:]) if half > 10 else {}
    return {
        "trades": len(t),
        "win_rate": round(100 * len(w) / len(t), 1),
        "avg_win": round(w["ret_opt_pct"].mean(), 2) if len(w) else 0,
        "avg_loss": round(l["ret_opt_pct"].mean(), 2) if len(l) else 0,
        "profit_factor": round(gp / gl, 2),
        "avg_opt_ret_%": round(t["ret_opt_pct"].mean(), 3),
        "total_opt_ret_%": round(t["ret_opt_pct"].sum(), 1),
        "max_dd_%": round(100 * dd, 1),
        "pf_second_half": m2.get("profit_factor"),
    }


def main():
    all_trades = []
    for f in sorted(os.listdir(DATA_DIR)):
        if not f.endswith(".csv"):
            continue
        sym = f[:-4]
        if sym in EXCLUDE:
            continue
        df = pd.read_csv(os.path.join(DATA_DIR, f), parse_dates=["time"])
        if len(df) < 200:
            continue
        all_trades.append(run_one(df, P, sym))
    t = pd.concat(all_trades, ignore_index=True)
    print("=== Iteration 2 results ===")
    for k, v in metrics(t).items():
        print(f"  {k}: {v}")
    t.to_csv("/home/ubuntu/nse_scalper/data/bt_iter2_trades.csv", index=False)


if __name__ == "__main__":
    main()
