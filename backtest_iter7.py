"""
backtest_iter7.py — Iteration 7.

Fixes the biggest bleed found in iter-6 (time-stop exits at -0.31% avg):
 1. No fixed time stop. Exit on STRUCTURE instead:
      - close < entry bar's low  -> momentum failed, get out
      - close < SMA9 (fast trend loss)
      - TP hit: 1.5 x ATR (kept)
      - SL: impulse low (kept, usually ~1.5-2 ATR away)
      - breakeven after +0.75 ATR (kept)
 2. Stronger impulse requirement: RVOL >= 2.5 (this is the "news fingerprint")
 3. Entry trigger refined: re-entry confirmation bar must also have RVOL >= 1.5
    (the pullback resolution itself needs volume)
 4. Liquidity gate: avg 5m bar volume > 30k (deeper universe still liquid)
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
    "start_bar": 12,          # 10:00
    "end_hour": 14,
    "lookback": 20,
    "rvol_period": 20,
    "rvol_impulse": 2.5,
    "rvol_entry": 1.5,
    "range_impulse_mult": 1.2,
    "pullback_window": 25,
    "tp_atr_mult": 1.5,
    "be_atr_mult": 0.75,
    "atr_period": 14,
    "sma_fast": 9,
    "delta": 0.6,
    "cost_pct": 0.0010,
    "max_atr_pct": 0.035,
    "min_bar_vol": 30_000,
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
    df["sma9"] = df["close"].rolling(p["sma_fast"]).mean()
    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    vol_avg = df["volume"].rolling(min(2340, len(df))).mean()
    if vol_avg.iloc[-1] < p["min_bar_vol"]:
        return pd.DataFrame()

    trades = []
    pos = None
    impulse = None

    for i in range(max(p["start_bar"], 60), len(df)):
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
            elif row["close"] < pos["entry_bar_low"]:
                exit_px, reason = row["close"], "weak"
            elif row["close"] < row["sma9"]:
                exit_px, reason = row["close"], "trend"
            if exit_px is not None:
                ret_points = exit_px - pos["entry"]
                opt_ret = ret_points * p["delta"] / pos["entry_px"] - p["cost_pct"]
                trades.append({"sym": sym, "day": day, "entry_time": pos["entry_time"],
                               "entry_px": pos["entry_px"], "exit_px": exit_px,
                               "ret_opt_pct": opt_ret * 100, "points": round(ret_points, 2),
                               "reason": reason})
                pos = None
            else:
                if not pos.get("be") and row["high"] >= pos["entry"] + p["be_atr_mult"] * pos["atr0"]:
                    pos["sl"] = pos["entry"]
                    pos["be"] = True
            continue

        if impulse is not None:
            impulse["count"] += 1
            hl_ok = row["low"] > impulse["low"]
            hold_ok = row["close"] > row["sma20"]
            if hl_ok and hold_ok and row["close"] > df["high"].iloc[i - 1] and row["rvol"] >= p["rvol_entry"]:
                tp = row["close"] + p["tp_atr_mult"] * impulse["atr"]
                sl = impulse["low"]
                pos = {"sym": sym, "bar": i, "entry": row["close"],
                       "entry_px": row["close"], "tp": tp, "sl": sl,
                       "atr0": impulse["atr"], "be": False,
                       "entry_bar_low": row["low"],
                       "entry_time": df["time"].iloc[i]}
                impulse = None
                continue
            elif row["low"] <= impulse["low"] or impulse["count"] > p["pullback_window"]:
                impulse = None
                continue

        if hour >= p["end_hour"]:
            continue
        hh = df["high"].iloc[i - p["lookback"]:i].max()
        bar_range = row["high"] - row["low"]
        close_pos = (row["close"] - row["low"]) / bar_range if bar_range > 0 else 0
        trend_ok = (pd.notna(row["sma50"]) and row["sma20"] > row["sma50"]
                    and row["sma50"] > df["sma50"].iloc[max(0, i - 10)])
        impulse_cond = (row["close"] > hh and row["rvol"] >= p["rvol_impulse"]
                        and bar_range >= p["range_impulse_mult"] * row["atr"]
                        and close_pos >= 0.4 and trend_ok
                        and row["atr"] / row["close"] <= p["max_atr_pct"])
        if impulse_cond:
            impulse = {"bar": i, "low": row["low"], "atr": row["atr"],
                       "close": row["close"], "count": 0}

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
    daily = t.groupby("day")["ret_opt_pct"].sum()
    return {
        "trades": len(t), "stocks_with_trades": t["sym"].nunique(),
        "days": t["day"].nunique(),
        "win_rate": round(100 * len(w) / len(t), 1),
        "avg_win": round(w["ret_opt_pct"].mean(), 2) if len(w) else 0,
        "avg_loss": round(l["ret_opt_pct"].mean(), 2) if len(l) else 0,
        "profit_factor": round(gp / gl, 2),
        "avg_opt_ret_%": round(t["ret_opt_pct"].mean(), 3),
        "total_opt_ret_%": round(t["ret_opt_pct"].sum(), 1),
        "max_dd_%": round(100 * dd, 1),
        "pf_second_half": m2.get("profit_factor"),
        "pct_profitable_days": round(100 * (daily > 0).mean(), 1),
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
        if len(df) < 400:
            continue
        tr = run_one(df, P, sym)
        if len(tr):
            all_trades.append(tr)
    t = pd.concat(all_trades, ignore_index=True)
    print("=== Iteration 7 results ===")
    for k, v in metrics(t).items():
        print(f"  {k}: {v}")
    t.to_csv("/home/ubuntu/nse_scalper/data/bt_iter7_trades.csv", index=False)
    print("\nBy exit reason:")
    print(t.groupby("reason").agg(n=("ret_opt_pct", "size"), mean=("ret_opt_pct", "mean")).to_string())


if __name__ == "__main__":
    main()
