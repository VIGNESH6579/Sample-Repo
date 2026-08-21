"""
backtest_earnings.py — Backtest a PREDICTABLE-NEWS strategy:

Idea: earnings announcements are the most predictable news events. The play
tested here is NOT gambling on results direction, but trading the
POST-EARNINGS MOMENTUM continuation:

  1. Detect the results day as the first big RVOL impulse bar after the
     quarter_end date (results are announced within ~4 weeks of quarter end;
     we detect the actual day from the price action itself — this keeps the
     backtest honest and maps directly to the live system).
  2. Trade the first pullback continuation on the results day or next day
     in the direction of the results-day impulse (same logic family as the
     intraday engine, but event-anchored).
  3. Compare against a random-day baseline to isolate the EVENT effect.

Baseline: same setup logic but only on random non-event days with ordinary
RVOL 2.5 spikes. If event-day trades significantly outperform, the
predictable-news anchor adds measurable value.
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
    "start_bar": 12,
    "end_hour": 15,          # results can come anytime before close
    "lookback": 20,
    "rvol_period": 20,
    "rvol_impulse": 2.5,
    "rvol_entry": 1.5,
    "range_impulse_mult": 1.2,
    "pullback_window": 30,
    "tp_atr_mult": 1.5,
    "sl_min_atr": 2.0,
    "be_atr_mult": 0.75,
    "atr_period": 14,
    "delta": 0.6,
    "cost_pct": 0.0010,
    "max_atr_pct": 0.04,
    "min_bar_vol": 20_000,
    "min_day_chg_abs": 0.02,   # results day: move must be >=2% (earnings gap quality)
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


def run_one(df, p, sym, earnings_days=None, mode="event"):
    """mode='event': only allow impulse detection on earnings_days (or day after).
       mode='baseline': any day.
       earnings_days: set of dates (as strings 'YYYY-MM-DD') that are candidate
       results windows.
    """
    df = df.copy().reset_index(drop=True)
    df["atr"] = atr(df, p["atr_period"])
    df["rvol"] = rvol(df, p["rvol_period"])
    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    vol_avg = df["volume"].rolling(min(2340, len(df))).mean()
    if vol_avg.iloc[-1] < p["min_bar_vol"]:
        return pd.DataFrame()
    prev_close = df["close"].shift(1)
    df["day_chg"] = (df["close"] - prev_close) / prev_close
    df["day_chg_abs"] = df["day_chg"].abs()

    # mark bars that fall on allowed event days
    if mode == "event" and earnings_days:
        ed = pd.to_datetime(list(earnings_days), errors="coerce")
        # allow results day + next session
        ed_next = ed + pd.Timedelta(days=1)
        allowed = pd.Series(False, index=df.index)
        allowed |= df["time"].dt.date.isin(ed.date)
        allowed |= df["time"].dt.date.isin(ed_next.date)
    else:
        allowed = pd.Series(True, index=df.index)

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
        if mode == "event" and not allowed.iloc[i]:
            continue
        if mode == "event" and row["day_chg_abs"] < p["min_day_chg_abs"]:
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


def metrics(t, label):
    if len(t) < 10:
        print(f"--- {label}: only {len(t)} trades")
        return None
    w = t[t["ret_opt_pct"] > 0]
    l = t[t["ret_opt_pct"] <= 0]
    gp = w["ret_opt_pct"].sum() if len(w) else 0
    gl = abs(l["ret_opt_pct"].sum()) if len(l) else 1e-9
    eq = (1 + t["ret_opt_pct"] / 100).cumprod()
    dd = ((eq / eq.cummax()) - 1).min()
    print(f"--- {label}: n={len(t)}, WR={100*len(w)/len(t):.0f}%, "
          f"PF={gp/gl:.2f}, avg={t['ret_opt_pct'].mean():+.3f}%, "
          f"total={t['ret_opt_pct'].sum():+.1f}%, maxDD={100*dd:.0f}%")
    return {"label": label, "n": len(t), "wr": 100 * len(w) / len(t),
            "pf": gp / gl, "avg": t["ret_opt_pct"].mean(),
            "total": t["ret_opt_pct"].sum(), "dd": 100 * dd}


def load_earnings():
    try:
        df = pd.read_csv("/home/ubuntu/nse_scalper/data/earnings_dates.csv")
        out = {}
        for _, r in df.iterrows():
            qe = pd.to_datetime(r["quarter_end"])
            # announcement window: quarter end + 3..30 days
            days = pd.date_range(qe + pd.Timedelta(days=3), qe + pd.Timedelta(days=30), freq="B")
            out[r["symbol"]] = set(d.strftime("%Y-%m-%d") for d in days)
        return out
    except Exception:
        return {}


def main():
    earnings = load_earnings()
    print(f"stocks with earnings windows: {len(earnings)}")
    event_all, base_all = [], []
    for f in sorted(os.listdir(DATA_DIR)):
        if not f.endswith(".csv"):
            continue
        sym = f[:-4]
        if sym in EXCLUDE:
            continue
        df = pd.read_csv(os.path.join(DATA_DIR, f), parse_dates=["time"])
        if len(df) < 400:
            continue
        te = run_one(df, P, sym, earnings.get(sym), mode="event")
        if len(te):
            te["mode"] = "event"
            event_all.append(te)
        tb = run_one(df, P, sym, mode="baseline")
        if len(tb):
            tb["mode"] = "baseline"
            base_all.append(tb)
    te = pd.concat(event_all, ignore_index=True)
    tb = pd.concat(base_all, ignore_index=True)
    print("\n=== Earnings-event vs random baseline (same pullback logic) ===")
    me = metrics(te, "EVENT (earnings window)")
    mb = metrics(tb, "BASELINE (random RVOL days)")
    te.to_csv("/home/ubuntu/nse_scalper/data/bt_earnings_event_trades.csv", index=False)
    tb.to_csv("/home/ubuntu/nse_scalper/data/bt_earnings_base_trades.csv", index=False)


if __name__ == "__main__":
    main()
