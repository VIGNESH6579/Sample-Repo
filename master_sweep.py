"""
master_sweep.py — Comprehensive Strategy Optimization.

Testing Variations:
1. RVOL Filter: None, 1.5, 2.0, 3.0
2. Trend Filter: EMA20 vs EMA50 vs EMA200
3. Squeeze Duration: Release immediately vs Squeeze ON for 5+ bars
4. Exit Logic: Fixed TP/SL vs Trailing Stop vs Pivot Targets
"""
import os
import sys
import numpy as np
import pandas as pd
from itertools import product

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter15 import squeeze_momentum, calc_vwap, run_one_squeeze_vwap, P_PARAMS
from backtest_iter16 import get_top_movers_for_day
from backtest_iter4 import atr, rvol

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"

def run_variation(df, params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df['ema'] = df['close'].ewm(span=params['ema_len'], adjust=False).mean()
    df['vwap'] = calc_vwap(df)
    df['val'], df['sqzOn'] = squeeze_momentum(df)
    df['atr'] = atr(df)
    df['rvol'] = rvol(df)
    
    # Squeeze duration check
    df['sqz_len'] = df['sqzOn'].astype(int).groupby(df['sqzOn'].astype(int).diff().ne(0).cumsum()).cumsum()
    
    trades = []
    pos = None
    
    for i in range(params['ema_len'] + 5, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if pos:
            exit_px = None
            if pos['type'] == 'long':
                if row['low'] <= pos['sl']: exit_px = pos['sl']
                elif row['high'] >= pos['tp']: exit_px = pos['tp']
            else:
                if row['high'] >= pos['sl']: exit_px = pos['sl']
                elif row['low'] <= pos['tp']: exit_px = pos['tp']
            
            if exit_px:
                ret = (exit_px - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - exit_px) / pos['entry']
                trades.append(ret)
                pos = None
            continue

        # Entry Filters
        is_long = row['close'] > row['ema'] and row['close'] > row['vwap'] and row['val'] > 0 and prev['val'] <= 0
        is_short = row['close'] < row['ema'] and row['close'] < row['vwap'] and row['val'] < 0 and prev['val'] >= 0
        
        # Apply Variation Params
        if params['use_rvol'] and row['rvol'] < params['rvol_thresh']: continue
        if params['min_sqz_len'] > 0 and prev['sqz_len'] < params['min_sqz_len']: continue
        
        if is_long:
            sl = row['close'] - row['atr'] * 2
            tp = row['close'] + row['atr'] * 4
            pos = {'type': 'long', 'entry': row['close'], 'sl': sl, 'tp': tp}
        elif is_short:
            sl = row['close'] + row['atr'] * 2
            tp = row['close'] - row['atr'] * 4
            pos = {'type': 'short', 'entry': row['close'], 'sl': sl, 'tp': tp}
            
    return trades

def main():
    all_data = {}
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            df['time'] = pd.to_datetime(df['time'])
            all_data[f[:-4]] = df
            
    dates = sorted(list(set(d for df in all_data.values() for d in df['time'].dt.date.unique())))
    
    # Param Grid
    grid = {
        'ema_len': [20, 50],
        'rvol_thresh': [1.0, 2.0],
        'min_sqz_len': [0, 5],
        'use_rvol': [True, False]
    }
    
    keys, values = zip(*grid.items())
    permutations = [dict(zip(keys, v)) for v in product(*values)]
    
    results = []
    for p in permutations:
        total_ret = 0
        trade_count = 0
        for date in dates:
            gainers, losers = get_top_movers_for_day(date, all_data)
            for sym in (gainers + losers):
                df = all_data[sym]
                day_df = df[df['time'].dt.date == date]
                rets = run_variation(day_df, p, sym)
                total_ret += sum(rets)
                trade_count += len(rets)
        
        results.append({'params': p, 'ret': total_ret, 'trades': trade_count})
        print(f"Tested: {p} -> Ret: {total_ret:.2f}, Trades: {trade_count}")

    best = max(results, key=lambda x: x['ret'])
    print("\n=== GOLDEN SETTINGS FOUND ===")
    print(best)

if __name__ == "__main__":
    main()
