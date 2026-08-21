"""
backtest_iter3.py — Iteration 3.

Diagnosis of iter-2: TP hits only +0.08% avg while SL costs -0.28% avg
(1:1 ATR is actually ~1:3.5 in option terms because winners get cut short by
the 12-bar time stop before TP is reached). Winners exit on TIME STOP mostly
at breakeven-ish levels; losers exit on SL at full distance.

Fixes:
 1. Asymmetric R:R in points: TP = 2.0 x ATR, SL = 1.0 x ATR
 2. Breakeven move: once price reaches +1.0 ATR, SL moves to entry (protects
    the trade — this was the missing ingredient; time-stop losers were losing
    full 1 ATR after being briefly in profit)
 3. Stronger trend alignment: close > SMA50 AND SMA20 > SMA50 (both MAs rising)
 4. Keep: RVOL >= 2.2, close in top 25% of bar, ATR% regime, 1 trade/day
 5. Extend trigger window to 9:45-13:00 (trend days develop late morning)
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
    "trigger_start_bar": 6,
    "trigger_end_hour": 13,
    "lookback_high": 20,
    "rvol_period": 20,
    "rvol_thresh": 2.2,
    "tp_atr_mult": 2.0,
    "sl_atr_mult": 1.0,
    "breakeven_atr": 1.0,     # move SL to entry after +1 ATR
    "atr_period": 14,
    "time_stop_bars": 18,
    "delta": 0.6,
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
    df["sma50"] = df["close"].rolling(50).mean()

    trades = []
    pos = None
    traded_days = set()

    for i in range(max(p["trigger_start_bar"], 60), len(df)):
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
            else:
                # breakeven rule: price made it +1 ATR at some point
                if not pos.get("be") and row["high"] >= pos["entry"] + p["breakeven_atr"] * pos["atr0"]:
                    pos["sl"] = pos["entry"]
                    pos["be"] = True
            continue

        if day in traded_days or hour >= p["trigger_end_hour"]:
            continue

        hh = df["high"].iloc[i - p["lookback_high"]:i].max()
        bar_range = row["high"] - row["low"]
        close_position = (row["close"] - row["low"]) / bar_range if bar_range > 0 else 0

        breakout = row["close"] > hh
        vol_ok = row["rvol"] >= p["rvol_thresh"]
        trend_ok = row["close"] > row["sma50"] and row["sma20"] > row["sma50"]
        strength_ok = close_position >= 0.75
        regime_ok = row["atr"] / row["close"] <= p["max_atr_pct"]
        if breakout and vol_ok and trend_ok and strength_ok and regime_ok:
            tp = row["close"] + p["tp_atr_mult"] * row["atr"]
            sl = row["close"] - p["sl_atr_mult"] * row["atr"]
            pos = {"sym": sym, "bar": i, "entry": row["close"],
                   "entry_px": row["close"], "tp": tp, "sl": sl,
                   "atr0": row["atr"], "be": False,
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
        if len(df) < 300:
            continue
        all_trades.append(run_one(df, P, sym))
    t = pd.concat(all_trades, ignore_index=True)
    print("=== Iteration 3 results ===")
    for k, v in metrics(t).items():
        print(f"  {k}: {v}")
    t.to_csv("/home/ubuntu/nse_scalper/data/bt_iter3_trades.csv", index=False)
    print("\nBy exit reason:")
    print(t.groupby("reason").agg(n=("ret_opt_pct", "size"), mean=("ret_opt_pct", "mean")).to_string())


if __name__ == "__main__":
    main()
