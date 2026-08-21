"""
backtest_iter10.py — Extreme Pivot Rejection (R3/S3).

Logic:
 1. Only trade REJECTIONS at R3 (Short) or S3 (Long). These are the 
    highest-probability setups shown in the user's Cipla screenshot.
 2. Confirmation: WaveTrend oscillator flip + price action (close back inside R3/S3).
 3. Exit: Fast EMA cross or next Pivot level.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"
EXCLUDE = {"SUZLON", "NBCC", "MAZDOCK", "JSWENERGY", "TORNTPOWER", "SYNGENE"}

P_PARAMS = {
    "wt_channel": 10,
    "wt_avg": 21,
    "cost_pct": 0.0010,
    "delta": 0.6,
}

def wavetrend(df, ch=10, avg=21):
    ap = (df['high'] + df['low'] + df['close']) / 3
    esa = ap.ewm(span=ch, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=ch, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d)
    tci = ci.ewm(span=avg, adjust=False).mean()
    return tci

def calc_pivots(df):
    daily = df.resample('D', on='time').agg({'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    daily_prev = daily.shift(1)
    p = (daily_prev['high'] + daily_prev['low'] + daily_prev['close']) / 3
    r3 = daily_prev['high'] + 2 * (p - daily_prev['low'])
    s3 = daily_prev['low'] - 2 * (daily_prev['high'] - p)
    r2 = p + (daily_prev['high'] - daily_prev['low'])
    s2 = p - (daily_prev['high'] - daily_prev['low'])
    return pd.DataFrame({'R3': r3, 'S3': s3, 'R2': r2, 'S2': s2})

def run_one(df, p_params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df['wt'] = wavetrend(df, p_params['wt_channel'], p_params['wt_avg'])
    df['wt_prev'] = df['wt'].shift(1)
    
    pivots = calc_pivots(df)
    pivots.index = pd.to_datetime(pivots.index).date
    df['date'] = df['time'].dt.date
    df = df.merge(pivots, left_on='date', right_index=True, how='left')
    
    trades = []
    pos = None
    
    for i in range(50, len(df)):
        row = df.iloc[i]
        
        if pos:
            exit_px = None
            if pos['type'] == 'long':
                if row['low'] <= pos['sl']: exit_px = pos['sl']
                elif row['high'] >= pos['tp']: exit_px = pos['tp']
                elif row['wt'] < 0: exit_px = row['close']
            else:
                if row['high'] >= pos['sl']: exit_px = pos['sl']
                elif row['low'] <= pos['tp']: exit_px = pos['tp']
                elif row['wt'] > 0: exit_px = row['close']
            
            if exit_px:
                ret = (exit_px - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - exit_px) / pos['entry']
                trades.append({'ret': ret * p_params['delta'] - p_params['cost_pct']})
                pos = None
            continue

        # Short at R3 Rejection
        if row['high'] >= row['R3'] and row['close'] < row['R3'] and row['wt'] < 0 and row['wt_prev'] >= 0:
            pos = {'type': 'short', 'entry': row['close'], 'sl': row['high'] * 1.005, 'tp': row['R2'], 'time': row['time']}
        
        # Long at S3 Rejection
        elif row['low'] <= row['S3'] and row['close'] > row['S3'] and row['wt'] > 0 and row['wt_prev'] <= 0:
            pos = {'type': 'long', 'entry': row['close'], 'sl': row['low'] * 0.995, 'tp': row['S2'], 'time': row['time']}

    return pd.DataFrame(trades)

def main():
    all_rets = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            tr = run_one(df, P_PARAMS, f[:-4])
            if not tr.empty: all_rets.append(tr)
    
    if not all_rets:
        print("No trades found.")
        return
    
    t = pd.concat(all_rets)
    print("=== Iteration 10: Extreme R3/S3 Rejection ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret'] > 0).mean()*100:.1f}%")
    print(f"Total Return: {t['ret'].sum()*100:.1f}%")

if __name__ == "__main__":
    main()
