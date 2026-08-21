"""
backtest_iter13.py — Vertical Drop / Momentum Scalp.

Logic:
 1. Consolidation: Price stays within 0.5% range for 10+ bars.
 2. Breakout: Price breaks below consolidation range with RVOL > 2.0.
 3. Context: Break happens near R2/R3 resistance zones.
 4. Exit: Scalp exit on 1.0% move or first bullish candle.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter10 import wavetrend, calc_pivots, P_PARAMS
from backtest_iter4 import rvol

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"

def run_one_vertical(df, p_params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df['rvol'] = rvol(df)
    
    pivots = calc_pivots(df)
    pivots.index = pd.to_datetime(pivots.index).date
    df['date'] = df['time'].dt.date
    df = df.merge(pivots, left_on='date', right_index=True, how='left')
    
    trades = []
    pos = None
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        
        if pos:
            exit_px = None
            if pos['type'] == 'short':
                if row['high'] >= pos['sl']: exit_px = pos['sl']
                elif row['low'] <= pos['tp']: exit_px = pos['tp']
                elif row['close'] > row['open']: exit_px = row['close'] # Exit on first green candle
            
            if exit_px:
                ret = (pos['entry'] - exit_px) / pos['entry']
                trades.append({'ret': ret * p_params['delta'] - p_params['cost_pct']})
                pos = None
            continue

        # Look for consolidation breakout at Resistance
        lookback = df.iloc[i-10:i]
        cons_range = (lookback['high'].max() - lookback['low'].min()) / lookback['low'].min()
        
        if cons_range < 0.005 and row['close'] < lookback['low'].min() and row['rvol'] > 2.0:
            if abs(row['high'] - row['R2'])/row['R2'] < 0.01 or abs(row['high'] - row['R3'])/row['R3'] < 0.01:
                pos = {'type': 'short', 'entry': row['close'], 'sl': lookback['high'].max(), 'tp': row['close'] * 0.98, 'time': row['time']}

    return pd.DataFrame(trades)

def main():
    all_rets = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            tr = run_one_vertical(df, P_PARAMS, f[:-4])
            if not tr.empty: all_rets.append(tr)
    
    if not all_rets:
        print("No trades found.")
        return
    
    t = pd.concat(all_rets)
    print("=== Iteration 13: Vertical Drop Momentum Results ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret'] > 0).mean()*100:.1f}%")
    print(f"Total Return: {t['ret'].sum()*100:.1f}%")

if __name__ == "__main__":
    main()
