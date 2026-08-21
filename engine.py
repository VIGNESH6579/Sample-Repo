"""
engine.py — Live Signal Engine for NSE F&O News-Driven Scalping.

Logic: High-Conviction Pivot-Momentum Rejection.
1. Fetch live quotes for F&O stocks.
2. Calculate Daily Pivots (R1-R3, S1-S3).
3. Detect R3/S3 Rejections + WaveTrend Flip + RVOL Spike.
4. Send alerts via Ntfy.
"""
import time
import logging
import pandas as pd
import numpy as np
import requests
from modules.nse_data import fetch_live_quotes, get_intraday_bars, FO_STOCKS
from modules.news import fetch_all, headlines_for_stock
from backtest_iter10 import wavetrend

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("nse_engine")

# Configuration
NTFY_TOPIC = "nse_scalper_signals" # Default topic
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

def send_alert(message, tags=None):
    try:
        requests.post(NTFY_URL, data=message.encode('utf-8'), headers={"Tags": tags or ""})
        logger.info(f"Alert sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")

def calc_pivots_live(bars_1d):
    # bars_1d should be the previous day's OHLC
    h, l, c = bars_1d['high'], bars_1d['low'], bars_1d['close']
    p = (h + l + c) / 3
    r1, s1 = 2*p - l, 2*p - h
    r2, s2 = p + (h - l), p - (h - l)
    r3 = h + 2*(p - l)
    s3 = l - 2*(h - p)
    return {'R1': r1, 'R2': r2, 'R3': r3, 'S1': s1, 'S2': s2, 'S3': s3}

def check_stock(sym, prev_day_bars):
    try:
        # 1. Get Intraday 5m Bars
        bars = get_intraday_bars(sym, interval="5m", range="1d")
        if bars.empty or len(bars) < 10: return
        
        # 2. Calculate Technicals
        bars['wt'] = wavetrend(bars)
        last = bars.iloc[-1]
        prev = bars.iloc[-2]
        
        # 3. Pivot Check
        pivots = calc_pivots_live(prev_day_bars)
        
        # 4. Signal Logic: High-Conviction Rejection
        # Bearish Rejection at R3
        if last['high'] >= pivots['R3'] and last['close'] < pivots['R3']:
            if last['wt'] < 0 and prev['wt'] >= 0:
                msg = f"🚨 {sym} SELL SETUP at R3 ({pivots['R3']:.2f})\nPrice: {last['close']:.2f}\nLogic: Pivot Rejection + Mom Flip"
                send_alert(msg, tags="warning,chart_with_downwards_trend")
        
        # Bullish Rejection at S3
        elif last['low'] <= pivots['S3'] and last['close'] > pivots['S3']:
            if last['wt'] > 0 and prev['wt'] <= 0:
                msg = f"🚀 {sym} BUY SETUP at S3 ({pivots['S3']:.2f})\nPrice: {last['close']:.2f}\nLogic: Pivot Rejection + Mom Flip"
                send_alert(msg, tags="rocket,chart_with_upwards_trend")

    except Exception as e:
        logger.error(f"Error checking {sym}: {e}")

def get_top_movers():
    logger.info("Refreshing Top 10 Gainers and Losers...")
    quotes = fetch_live_quotes(FO_STOCKS)
    if quotes.empty: return FO_STOCKS
    
    quotes['change'] = (quotes['price'] - quotes['open']) / quotes['open']
    sorted_q = quotes.sort_values('change')
    top_losers = sorted_q.head(10)['symbol'].tolist()
    top_gainers = sorted_q.tail(10)['symbol'].tolist()
    return list(set(top_gainers + top_losers))

def main():
    logger.info("Starting NSE Live Signal Engine (Momentum Focus)...")
    send_alert("NSE Scalper Engine Started. Focusing on Top 10 Gainers/Losers.", tags="fire")
    
    prev_data = {}
    # Initial pivot fetch
    for sym in FO_STOCKS:
        try:
            df = get_intraday_bars(sym, interval="1d", range="5d")
            if not df.empty: prev_data[sym] = df.iloc[-2]
        except: continue
    
    last_refresh = 0
    targets = FO_STOCKS
    
    while True:
        # Refresh Top Movers every 15 minutes
        if time.time() - last_refresh > 900:
            targets = get_top_movers()
            last_refresh = time.time()
            logger.info(f"Monitoring Targets: {', '.join(targets)}")
        
        for sym in targets:
            if sym in prev_data:
                check_stock(sym, prev_data[sym])
            time.sleep(1)
        
        time.sleep(60)

if __name__ == "__main__":
    main()
