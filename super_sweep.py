"""
super_sweep.py — Cracking the Win Rate.

Testing High-Probability Filters:
1. NIFTY Alignment: Only trade if stock is moving with NIFTY (Trend Sync).
2. Trailing Stop: 1.0x ATR trailing stop to lock in profits early.
3. Time Window: Avoid 9:15-10:00 (high noise), trade 10:00-14:30.
4. Profit-Taking: Smaller TP (1.5R or 2R) to increase win frequency.
"""
import os
import sys
import numpy as np
import pandas as pd
from itertools import product

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter15 import squeeze_momentum, calc_vwap, P_PARAMS
from backtest_iter16 import get_top_movers_for_day
from backtest_iter4 import atr, rvol

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"

def run_super_variation(df, nifty_df, params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df['ema'] = df['close'].ewm(span=50, adjust=False).mean()
    df['vwap'] = calc_vwap(df)
    df['val'], df['sqzOn'] = squeeze_momentum(df)
    df['atr'] = atr(df)
    
    # NIFTY Sync
    nifty_df = nifty_df.copy()
    nifty_df['time'] = pd.to_datetime(nifty_df['time'])
    nifty_df['nifty_ema'] = nifty_df['close'].ewm(span=50, adjust=False).mean()
    df = df.merge(nifty_df[['time', 'nifty_ema', 'close']], on='time', how='left', suffixes=('', '_nifty'))
    
    trades = []
    pos = None
    
    for i in range(50, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if pos:
            exit_px = None
            if pos['type'] == 'long':
                if row['low'] <= pos['sl']: exit_px = pos['sl']
                elif row['high'] >= pos['tp']: exit_px = pos['tp']
                # Trailing Stop
                if params['trailing']:
                    new_sl = row['close'] - row['atr'] * 1.5
                    if new_sl > pos['sl']: pos['sl'] = new_sl
            else:
                if row['high'] >= pos['sl']: exit_px = pos['sl']
                elif row['low'] <= pos['tp']: exit_px = pos['tp']
                # Trailing Stop
                if params['trailing']:
                    new_sl = row['close'] + row['atr'] * 1.5
                    if new_sl < pos['sl']: pos['sl'] = new_sl
            
            if exit_px:
                ret = (exit_px - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - exit_px) / pos['entry']
                trades.append(ret)
                pos = None
            continue

        # Time Window Filter
        if not (10 <= row['time'].hour <= 14): continue
        
        # NIFTY Sync Filter
        if params['nifty_sync']:
            nifty_bull = row['close_nifty'] > row['nifty_ema']
            nifty_bear = row['close_nifty'] < row['nifty_ema']
        else:
            nifty_bull = nifty_bear = True

        # Signal
        is_long = row['close'] > row['ema'] and row['close'] > row['vwap'] and row['val'] > 0 and prev['val'] <= 0 and nifty_bull
        is_short = row['close'] < row['ema'] and row['close'] < row['vwap'] and row['val'] < 0 and prev['val'] >= 0 and nifty_bear
        
        if is_long:
            sl = row['close'] - row['atr'] * 2
            tp = row['close'] + row['atr'] * params['tp_mult']
            pos = {'type': 'long', 'entry': row['close'], 'sl': sl, 'tp': tp}
        elif is_short:
            sl = row['close'] + row['atr'] * 2
            tp = row['close'] - row['atr'] * params['tp_mult']
            pos = {'type': 'short', 'entry': row['close'], 'sl': sl, 'tp': tp}
            
    return trades

def main():
    all_data = {}
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            df['time'] = pd.to_datetime(df['time'])
            all_data[f[:-4]] = df
            
    nifty_df = all_data.get('NIFTY', all_data.get('RELIANCE')) # Use NIFTY or proxy
    dates = sorted(list(set(d for df in all_data.values() for d in df['time'].dt.date.unique())))
    
    grid = {
        'nifty_sync': [True, False],
        'trailing': [True, False],
        'tp_mult': [1.5, 2.0, 3.0]
    }
    
    keys, values = zip(*grid.items())
    permutations = [dict(zip(keys, v)) for v in product(*values)]
    
    results = []
    for p in permutations:
        all_rets = []
        for date in dates:
            gainers, losers = get_top_movers_for_day(date, all_data)
            for sym in (gainers + losers):
                rets = run_super_variation(all_data[sym][all_data[sym]['time'].dt.date == date], nifty_df, p, sym)
                all_rets.extend(rets)
        
        if all_rets:
            wr = sum(1 for r in all_rets if r > 0) / len(all_rets)
            total_ret = sum(all_rets)
            results.append({'params': p, 'wr': wr, 'ret': total_ret, 'trades': len(all_rets)})
            print(f"WR: {wr*100:.1f}%, Ret: {total_ret:.2f}, Trades: {len(all_rets)} | Params: {p}")

    best_wr = max(results, key=lambda x: x['wr'])
    print("\n=== HIGHEST WIN RATE CRACKED ===")
    print(best_wr)

if __name__ == "__main__":
    main()
