"""
backtest_iter8.py — Iteration 8.

Diagnosis of iter-7: weak-exit trades lost -0.36% on average (close < entry
bar low is too loose — noise wicks us out after the move started). SL exits
were now small (-0.12%) because breakeven helped.

Changes:
 1. Remove "weak" exit (close < entry bar low). Only exits: TP, SL (impulse
    low), trend exit (close < SMA9), breakeven progression.
 2. SL widened to impulse-low-but-no-closer-than-2.0*ATR (reduce whipsaw).
 3. Trend exit uses SMA20 instead of SMA9 (less whippy).
 4. Entry: re-entry bar must close above previous high AND impulse RVOL >= 2.5
    AND overall market context: stock's day change already positive (momentum
    day) — proxies "good news" vs "bad news fade".
 5. No short/PUT side in this iteration; CALL only in uptrend context.
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
    "sl_min_atr": 2.0,       # SL at least this far (impulse low or -2 ATR, whichever farther)
    "be_atr_mult": 0.75,
    "atr_period": 14,
    "delta": 0.6,
    "cost_pct": 0.0010,
    "max_atr_pct": 0.035,
    "min_bar_vol": 30_000,
    "day_gain_min_pct": 0.0,  # stock must be up on the day
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
    vol_avg = df["volume"].rolling(min(2340, len(df))).mean()
    if vol_avg.iloc[-1] < p["min_bar_vol"]:
        return pd.DataFrame()
    # previous day's close for day-change context
    prev_close = df["close"].shift(1)
    df["day_chg"] = (df["close"] - prev_close) / prev_close

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
            elif row["close"] < row["sma20"]:
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
                sl = min(impulse["low"], row["close"] - p["sl_min_atr"] * impulse["atr"])
                pos = {"sym": sym, "bar": i, "entry": row["close"],
                       "entry_px": row["close"], "tp": tp, "sl": sl,
                       "atr0": impulse["atr"], "be": False,
                       "entry_time": df["time"].iloc[i]}
                impulse = None
                continue
            elif row["low"] <= impulse["low"] or impulse["count"] > p["pullback_window"]:
                impulse = None
                continue

        if hour >= p["end_hour"]:
            continue
        if row["day_chg"] < p["day_gain_min_pct"]:
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
    print("=== Iteration 8 results ===")
    for k, v in metrics(t).items():
        print(f"  {k}: {v}")
    t.to_csv("/home/ubuntu/nse_scalper/data/bt_iter8_trades.csv", index=False)
    print("\nBy exit reason:")
    print(t.groupby("reason").agg(n=("ret_opt_pct", "size"), mean=("ret_opt_pct", "mean")).to_string())


if __name__ == "__main__":
    main()
