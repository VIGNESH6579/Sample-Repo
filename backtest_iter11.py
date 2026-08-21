"""
backtest_iter11.py — News-Confirmed Pivot Rejection.

Logic:
 1. Strategy from Iteration 10 (R3/S3 rejection).
 2. NEWS FILTER: Only trade if the stock has a news headline in our 
    news_archive.db within 24 hours of the trade.
"""
import os
import sys
import sqlite3
import pandas as pd
import numpy as np

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter10 import wavetrend, calc_pivots, P_PARAMS

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"
DB_PATH = "/home/ubuntu/nse_scalper/news_archive.db"

def get_news_days(sym):
    try:
        conn = sqlite3.connect(DB_PATH)
        # Table name is 'headlines', columns are 'title' and 'pub_time'
        query = f"SELECT pub_time FROM headlines WHERE title LIKE '%{sym}%'"
        df = pd.read_sql(query, conn)
        conn.close()
        if df.empty: return set()
        return set(pd.to_datetime(df['pub_time']).dt.date)
    except:
        return set()

def run_one_news(df, p_params, sym, news_days):
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

        # News Filter: only trade if today is a news day for this stock
        if row['date'] not in news_days:
            continue

        if row['high'] >= row['R3'] and row['close'] < row['R3'] and row['wt'] < 0 and row['wt_prev'] >= 0:
            pos = {'type': 'short', 'entry': row['close'], 'sl': row['high'] * 1.005, 'tp': row['R2'], 'time': row['time']}
        elif row['low'] <= row['S3'] and row['close'] > row['S3'] and row['wt'] > 0 and row['wt_prev'] <= 0:
            pos = {'type': 'long', 'entry': row['close'], 'sl': row['low'] * 0.995, 'tp': row['S2'], 'time': row['time']}

    return pd.DataFrame(trades)

def main():
    all_rets = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            sym = f[:-4]
            news_days = get_news_days(sym)
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            tr = run_one_news(df, P_PARAMS, sym, news_days)
            if not tr.empty: all_rets.append(tr)
    
    if not all_rets:
        print("No trades found with news filter.")
        return
    
    t = pd.concat(all_rets)
    print("=== Iteration 11: News-Confirmed R3/S3 Rejection ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret'] > 0).mean()*100:.1f}%")
    print(f"Total Return: {t['ret'].sum()*100:.1f}%")

if __name__ == "__main__":
    main()
