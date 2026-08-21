"""
backtest_iter14.py — The "Vertical Drop" Reversal.

Logic:
 1. Strategy: Short at R3 rejection.
 2. Filter: Only if ATR is at a 20-bar low (Volatility Squeeze) BEFORE the rejection.
 3. Entry: Bearish Engulfing or Pin Bar at R3.
 4. Exit: Trailing stop at 1.0 x ATR to capture the "Vertical" move.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter10 import calc_pivots, P_PARAMS
from backtest_iter4 import atr

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"

def run_one_squeeze(df, p_params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df['atr'] = atr(df)
    df['atr_min'] = df['atr'].rolling(20).min()
    
    pivots = calc_pivots(df)
    pivots.index = pd.to_datetime(pivots.index).date
    df['date'] = df['time'].dt.date
    df = df.merge(pivots, left_on='date', right_index=True, how='left')
    
    trades = []
    pos = None
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if pos:
            exit_px = None
            if pos['type'] == 'short':
                if row['high'] >= pos['sl']: exit_px = pos['sl']
                elif row['low'] <= pos['tp']: exit_px = pos['tp']
                # Trailing stop
                new_sl = row['close'] + row['atr']
                if new_sl < pos['sl']: pos['sl'] = new_sl
            
            if exit_px:
                ret = (pos['entry'] - exit_px) / pos['entry']
                trades.append({'ret': ret * p_params['delta'] - p_params['cost_pct']})
                pos = None
            continue

        # Squeeze Rejection Signal
        is_squeeze = prev['atr'] <= prev['atr_min']
        is_rejection = row['high'] >= row['R3'] and row['close'] < row['R3']
        is_bearish = row['close'] < row['open']
        
        if is_squeeze and is_rejection and is_bearish:
            pos = {'type': 'short', 'entry': row['close'], 'sl': row['high'], 'tp': row['close'] * 0.95, 'time': row['time']}

    return pd.DataFrame(trades)

def main():
    all_rets = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            tr = run_one_squeeze(df, P_PARAMS, f[:-4])
            if not tr.empty: all_rets.append(tr)
    
    if not all_rets:
        print("No trades found.")
        return
    
    t = pd.concat(all_rets)
    print("=== Iteration 14: Squeeze Rejection Results ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret'] > 0).mean()*100:.1f}%")
    print(f"Total Return: {t['ret'].sum()*100:.1f}%")

if __name__ == "__main__":
    main()
