"""
backtest_iter15.py — Requested Squeeze-Momentum + VWAP Strategy.

Logic:
 1. Indicators: EMA20, Session VWAP, Daily Pivots, Squeeze Momentum (LazyBear).
 2. Long Entry: Close > EMA20, Close > VWAP, Squeeze flip (red->green), Squeeze release (1-3 bars).
 3. Short Entry: Mirror logic.
 4. Exit: ATR-based SL, Pivot-based TP, EOD exit at 15:15.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter10 import P_PARAMS

def calc_pivots(df):
    daily = df.resample('D', on='time').agg({'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    daily_prev = daily.shift(1)
    p = (daily_prev['high'] + daily_prev['low'] + daily_prev['close']) / 3
    r1 = 2 * p - daily_prev['low']
    s1 = 2 * p - daily_prev['high']
    r2 = p + (daily_prev['high'] - daily_prev['low'])
    s2 = p - (daily_prev['high'] - daily_prev['low'])
    r3 = daily_prev['high'] + 2 * (p - daily_prev['low'])
    s3 = daily_prev['low'] - 2 * (daily_prev['high'] - p)
    return pd.DataFrame({'P': p, 'R1': r1, 'S1': s1, 'R2': r2, 'S2': s2, 'R3': r3, 'S3': s3})
from backtest_iter4 import atr

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"

def linreg(series, length):
    x = np.arange(length)
    y = series.values
    def _calc(y_slice):
        if len(y_slice) < length: return 0
        slope, intercept = np.polyfit(x, y_slice, 1)
        return slope * (length - 1) + intercept
    return series.rolling(length).apply(_calc, raw=True)

def squeeze_momentum(df, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5):
    # Bollinger Bands
    basis = df['close'].rolling(bb_len).mean()
    dev = bb_mult * df['close'].rolling(bb_len).std()
    upperBB = basis + dev
    lowerBB = basis - dev
    
    # Keltner Channels
    tr = pd.concat([df['high'] - df['low'], 
                    (df['high'] - df['close'].shift(1)).abs(), 
                    (df['low'] - df['close'].shift(1)).abs()], axis=1).max(axis=1)
    ma = df['close'].rolling(kc_len).mean()
    range_ma = tr.rolling(kc_len).mean()
    upperKC = ma + range_ma * kc_mult
    lowerKC = ma - range_ma * kc_mult
    
    # Squeeze
    sqzOn = (lowerBB > lowerKC) & (upperBB < upperKC)
    
    # Momentum Value
    highestH = df['high'].rolling(kc_len).max()
    lowestL = df['low'].rolling(kc_len).min()
    avg = (highestH + lowestL) / 2
    val = linreg(df['close'] - (avg + df['close'].rolling(kc_len).mean()) / 2, kc_len)
    
    return val, sqzOn

def calc_vwap(df):
    df['date'] = pd.to_datetime(df['time']).dt.date
    v = df['volume']
    p = (df['high'] + df['low'] + df['close']) / 3
    return (p * v).groupby(df['date']).cumsum() / v.groupby(df['date']).cumsum()

def run_one_squeeze_vwap(df, p_params, sym):
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['vwap'] = calc_vwap(df)
    df['val'], df['sqzOn'] = squeeze_momentum(df)
    df['atr'] = atr(df)
    
    # Squeeze release within last 3 bars
    df['sqz_off'] = (~df['sqzOn']).astype(bool)
    # Correcting squeeze release logic: squeeze was ON 3 bars ago and is OFF now
    df['sqz_release'] = (df['sqzOn'].shift(3) == True) & (df['sqzOn'] == False)
    
    pivots = calc_pivots(df)
    pivots.index = pd.to_datetime(pivots.index).date
    df['date_only'] = df['time'].dt.date
    df = df.merge(pivots, left_on='date_only', right_index=True, how='left')
    
    trades = []
    pos = None
    
    for i in range(25, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if pos:
            exit_px = None
            if pos['type'] == 'long':
                if row['low'] <= pos['sl']: exit_px = pos['sl']
                elif row['high'] >= pos['tp']: exit_px = pos['tp']
                elif row['time'].hour == 15 and row['time'].minute >= 15: exit_px = row['close']
            else:
                if row['high'] >= pos['sl']: exit_px = pos['sl']
                elif row['low'] <= pos['tp']: exit_px = pos['tp']
                elif row['time'].hour == 15 and row['time'].minute >= 15: exit_px = row['close']
            
            if exit_px:
                ret = (exit_px - pos['entry']) / pos['entry'] if pos['type'] == 'long' else (pos['entry'] - exit_px) / pos['entry']
                trades.append({'ret': ret * p_params['delta'] - p_params['cost_pct']})
                pos = None
            continue

        # Long Entry
        if row['close'] > row['ema20'] and row['close'] > row['vwap']:
            if row['val'] > 0 and prev['val'] <= 0 and row['sqz_release']:
                sl = row['close'] - row['atr'] * 1.5
                tp = row['R1'] if row['close'] < row['R1'] else row['R2']
                pos = {'type': 'long', 'entry': row['close'], 'sl': sl, 'tp': tp, 'time': row['time']}
        
        # Short Entry
        elif row['close'] < row['ema20'] and row['close'] < row['vwap']:
            if row['val'] < 0 and prev['val'] >= 0 and row['sqz_release']:
                sl = row['close'] + row['atr'] * 1.5
                tp = row['S1'] if row['close'] > row['S1'] else row['S2']
                pos = {'type': 'short', 'entry': row['close'], 'sl': sl, 'tp': tp, 'time': row['time']}

    return pd.DataFrame(trades)

def main():
    all_rets = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            tr = run_one_squeeze_vwap(df, P_PARAMS, f[:-4])
            if not tr.empty: all_rets.append(tr)
    
    if not all_rets:
        print("No trades found.")
        return
    
    t = pd.concat(all_rets)
    print("=== Iteration 15: Squeeze-Momentum + VWAP Results ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret'] > 0).mean()*100:.1f}%")
    print(f"Total Return: {t['ret'].sum()*100:.1f}%")

if __name__ == "__main__":
    main()
