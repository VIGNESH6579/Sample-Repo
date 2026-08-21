"""
backtest_iter9.py — Pivot-Momentum Strategy (based on user screenshots).

Logic:
 1. Standard Daily Pivots: 
    P = (H+L+C)/3, R1 = 2P-L, S1 = 2P-H, R2 = P+(H-L), S2 = P-(H-L), R3 = H+2(P-L)
 2. 200 EMA Master Filter: Price > 200 EMA for Longs, < 200 EMA for Shorts.
 3. Momentum Histogram (WaveTrend proxy):
    - Channel Length 10, Average Length 21.
    - Signal: Bullish flip (Osc crosses above 0) or Bearish flip (Osc crosses below 0).
 4. Strategy:
    - Long: Price touches/bounces from S2/S3 OR breaks R2 + Bullish Mom + > 200 EMA.
    - Short: Price touches/reverses from R2/R3 + Bearish Mom + < 200 EMA.
 5. Exits: Next Pivot level or EMA cross.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"
EXCLUDE = {"SUZLON", "NBCC", "MAZDOCK", "JSWENERGY", "TORNTPOWER", "SYNGENE"}

P_PARAMS = {
    "ema_slow": 200,
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
    # Calculate daily pivots from the previous day's H, L, C
    daily = df.resample('D', on='time').agg({'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    daily_prev = daily.shift(1)
    
    p = (daily_prev['high'] + daily_prev['low'] + daily_prev['close']) / 3
    r1 = 2 * p - daily_prev['low']
    s1 = 2 * p - daily_prev['high']
    r2 = p + (daily_prev['high'] - daily_prev['low'])
    s2 = p - (daily_prev['high'] - daily_prev['low'])
    r3 = daily_prev['high'] + 2 * (p - daily_prev['low'])
    s3 = daily_prev['low'] - 2 * (daily_prev['high'] - p)
    
    pivots = pd.DataFrame({'P': p, 'R1': r1, 'S1': s1, 'R2': r2, 'S2': s2, 'R3': r3, 'S3': s3})
    return pivots

def run_one(df, p_params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    
    # Technicals
    df['ema200'] = df['close'].ewm(span=p_params['ema_slow'], adjust=False).mean()
    df['wt'] = wavetrend(df, p_params['wt_channel'], p_params['wt_avg'])
    df['wt_prev'] = df['wt'].shift(1)
    
    # Pivots
    pivots = calc_pivots(df)
    pivots.index = pd.to_datetime(pivots.index).date
    df['date'] = df['time'].dt.date
    df = df.merge(pivots, left_on='date', right_index=True, how='left')
    
    trades = []
    pos = None
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        # --- Manage Position ---
        if pos:
            exit_px = None
            reason = ""
            
            if pos['type'] == 'long':
                if row['low'] <= pos['sl']:
                    exit_px, reason = pos['sl'], 'sl'
                elif row['high'] >= pos['tp']:
                    exit_px, reason = pos['tp'], 'tp'
                elif row['wt'] < 0 and row['wt_prev'] >= 0: # Bearish Mom Flip
                    exit_px, reason = row['close'], 'mom_flip'
            else: # short
                if row['high'] >= pos['sl']:
                    exit_px, reason = pos['sl'], 'sl'
                elif row['low'] <= pos['tp']:
                    exit_px, reason = pos['tp'], 'tp'
                elif row['wt'] > 0 and row['wt_prev'] <= 0: # Bullish Mom Flip
                    exit_px, reason = row['close'], 'mom_flip'
            
            if exit_px:
                ret = (exit_px - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - exit_px) / pos['entry']
                opt_ret = ret * p_params['delta'] - p_params['cost_pct']
                trades.append({
                    'sym': sym, 'type': pos['type'], 'entry_time': pos['time'], 
                    'entry': pos['entry'], 'exit': exit_px, 'ret_pct': opt_ret * 100, 'reason': reason
                })
                pos = None
            continue

        # --- Signal Logic ---
        # Long: Price bounces S2/S3 or breaks R1 + Bullish Mom + > EMA200
        if row['close'] > row['ema200'] and row['wt'] > 0 and row['wt_prev'] <= 0:
            if row['low'] <= row['S2'] or row['low'] <= row['S3'] or (row['close'] > row['R1'] and prev['close'] <= row['R1']):
                tp = row['R2'] if row['close'] < row['R2'] else row['R3']
                sl = min(row['low'], row['S1'])
                pos = {'type': 'long', 'entry': row['close'], 'sl': sl, 'tp': tp, 'time': row['time']}
        
        # Short: Price rejects R2/R3 + Bearish Mom + < EMA200
        elif row['close'] < row['ema200'] and row['wt'] < 0 and row['wt_prev'] >= 0:
            if row['high'] >= row['R2'] or row['high'] >= row['R3'] or (row['close'] < row['S1'] and prev['close'] >= row['S1']):
                tp = row['S2'] if row['close'] > row['S2'] else row['S3']
                sl = max(row['high'], row['R1'])
                pos = {'type': 'short', 'entry': row['close'], 'sl': sl, 'tp': tp, 'time': row['time']}

    return pd.DataFrame(trades)

def main():
    all_trades = []
    for f in os.listdir(DATA_DIR):
        if not f.endswith(".csv"): continue
        sym = f[:-4]
        if sym in EXCLUDE: continue
        df = pd.read_csv(os.path.join(DATA_DIR, f))
        tr = run_one(df, P_PARAMS, sym)
        if not tr.empty: all_trades.append(tr)
    
    if not all_trades:
        print("No trades found.")
        return

    t = pd.concat(all_trades)
    print("=== Iteration 9: Pivot-Momentum Results ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret_pct'] > 0).mean()*100:.1f}%")
    print(f"Profit Factor: {t[t['ret_pct']>0]['ret_pct'].sum() / abs(t[t['ret_pct']<0]['ret_pct'].sum()):.2f}")
    print(f"Total Return: {t['ret_pct'].sum():.1f}%")

if __name__ == "__main__":
    main()
