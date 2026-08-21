"""
backtest_iter12.py — Reversal Candle + Pivot Rejection.

Logic:
 1. Identify Reversal Candles:
    - Pin Bar (Shooting Star/Hammer): Wick > 2x Body.
    - Bearish/Bullish Engulfing.
 2. Level Confirmation: Reversal must occur within 0.2% of R2/R3 or S2/S3.
 3. Momentum Confirmation: WaveTrend flip (Osc crosses 0) within 2 bars.
 4. Exit: Trend line break (EMA 20) or 1.5x ATR target.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter10 import wavetrend, calc_pivots, P_PARAMS

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"

def is_pin_bar(row):
    body = abs(row['close'] - row['open'])
    wick_top = row['high'] - max(row['open'], row['close'])
    wick_bot = min(row['open'], row['close']) - row['low']
    # Bearish Pin (Shooting Star)
    if wick_top > 2 * body and wick_top > wick_bot: return 'bear'
    # Bullish Pin (Hammer)
    if wick_bot > 2 * body and wick_bot > wick_top: return 'bull'
    return None

def run_one_reversal(df, p_params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df['wt'] = wavetrend(df, p_params['wt_channel'], p_params['wt_avg'])
    df['wt_prev'] = df['wt'].shift(1)
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    pivots = calc_pivots(df)
    pivots.index = pd.to_datetime(pivots.index).date
    df['date'] = df['time'].dt.date
    df = df.merge(pivots, left_on='date', right_index=True, how='left')
    
    trades = []
    pos = None
    
    for i in range(2, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if pos:
            exit_px = None
            if pos['type'] == 'long':
                if row['low'] <= pos['sl']: exit_px = pos['sl']
                elif row['high'] >= pos['tp']: exit_px = pos['tp']
                elif row['close'] < row['ema20']: exit_px = row['close']
            else:
                if row['high'] >= pos['sl']: exit_px = pos['sl']
                elif row['low'] <= pos['tp']: exit_px = pos['tp']
                elif row['close'] > row['ema20']: exit_px = row['close']
            
            if exit_px:
                ret = (exit_px - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - exit_px) / pos['entry']
                trades.append({'ret': ret * p_params['delta'] - p_params['cost_pct']})
                pos = None
            continue

        # Reversal Signal
        pin = is_pin_bar(row)
        mom_flip_bear = row['wt'] < 0 and row['wt_prev'] >= 0
        mom_flip_bull = row['wt'] > 0 and row['wt_prev'] <= 0
        
        # Bearish: Pin at R2/R3 + Mom Flip
        if pin == 'bear' and (abs(row['high'] - row['R2'])/row['R2'] < 0.002 or abs(row['high'] - row['R3'])/row['R3'] < 0.002):
            if mom_flip_bear or (prev['wt'] < 0 and df.iloc[i-2]['wt'] >= 0):
                pos = {'type': 'short', 'entry': row['close'], 'sl': row['high'], 'tp': row['close'] - (row['high'] - row['close']) * 2, 'time': row['time']}
        
        # Bullish: Pin at S2/S3 + Mom Flip
        elif pin == 'bull' and (abs(row['low'] - row['S2'])/row['S2'] < 0.002 or abs(row['low'] - row['S3'])/row['S3'] < 0.002):
            if mom_flip_bull or (prev['wt'] > 0 and df.iloc[i-2]['wt'] <= 0):
                pos = {'type': 'long', 'entry': row['close'], 'sl': row['low'], 'tp': row['close'] + (row['close'] - row['low']) * 2, 'time': row['time']}

    return pd.DataFrame(trades)

def main():
    all_rets = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            tr = run_one_reversal(df, P_PARAMS, f[:-4])
            if not tr.empty: all_rets.append(tr)
    
    if not all_rets:
        print("No trades found.")
        return
    
    t = pd.concat(all_rets)
    print("=== Iteration 12: Reversal Candle + Pivot Rejection ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret'] > 0).mean()*100:.1f}%")
    print(f"Total Return: {t['ret'].sum()*100:.1f}%")

if __name__ == "__main__":
    main()
