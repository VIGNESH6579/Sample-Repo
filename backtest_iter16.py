"""
backtest_iter16.py — Top 10 Gainers/Losers Momentum Strategy.

Logic:
 1. Each day at 10:00 AM (after initial volatility), rank all F&O stocks by % change.
 2. Pick Top 10 Gainers and Top 10 Losers.
 3. Apply the Squeeze-Momentum + VWAP strategy ONLY to these 20 stocks for the rest of the day.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from backtest_iter15 import run_one_squeeze_vwap, P_PARAMS

DATA_DIR = "/home/ubuntu/nse_scalper/data/hist"

def get_top_movers_for_day(date, all_data):
    movers = []
    for sym, df in all_data.items():
        day_data = df[df['time'].dt.date == date]
        if day_data.empty: continue
        
        # Calculate % change from open to 10:00 AM
        morning = day_data[(day_data['time'].dt.hour < 10)]
        if morning.empty: continue
        
        open_px = morning.iloc[0]['open']
        curr_px = morning.iloc[-1]['close']
        pct_change = (curr_px - open_px) / open_px
        movers.append({'sym': sym, 'change': pct_change})
    
    if not movers: return [], []
    
    movers_df = pd.DataFrame(movers).sort_values('change')
    top_losers = movers_df.head(10)['sym'].tolist()
    top_gainers = movers_df.tail(10)['sym'].tolist()
    return top_gainers, top_losers

def main():
    # Load all data into memory for ranking
    all_data = {}
    dates = set()
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_DIR, f))
            df['time'] = pd.to_datetime(df['time'])
            all_data[f[:-4]] = df
            dates.update(df['time'].dt.date.unique())
    
    sorted_dates = sorted(list(dates))
    all_trades = []
    
    print(f"Backtesting Top 10 Movers strategy over {len(sorted_dates)} days...")
    
    for date in sorted_dates:
        gainers, losers = get_top_movers_for_day(date, all_data)
        targets = gainers + losers
        if not targets: continue
        
        for sym in targets:
            df = all_data[sym]
            # Filter data for this specific day
            day_df = df[df['time'].dt.date == date]
            tr = run_one_squeeze_vwap(day_df, P_PARAMS, sym)
            if not tr.empty: all_trades.append(tr)
            
    if not all_trades:
        print("No trades found.")
        return
    
    t = pd.concat(all_trades)
    print("=== Iteration 16: Top 10 Gainers/Losers Results ===")
    print(f"Total Trades: {len(t)}")
    print(f"Win Rate: {(t['ret'] > 0).mean()*100:.1f}%")
    print(f"Total Return: {t['ret'].sum()*100:.1f}%")

if __name__ == "__main__":
    main()
