"""
engine.py — Live Signal Engine for NSE F&O Momentum Scalping.

Logic: Golden Squeeze-Momentum Strategy.
1. Monitors Top 10 Gainers and Losers (refreshed every 15m).
2. Filters: EMA 50 + VWAP + Squeeze Momentum (Min 5 bars) + RVOL > 2.0.
3. Sends alerts via Ntfy.
"""
import time
import logging
import pandas as pd
import numpy as np
import requests
from modules.nse_data import fetch_live_quotes, get_intraday_bars, FO_STOCKS
from backtest_iter15 import squeeze_momentum, calc_vwap
from backtest_iter4 import atr, rvol

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("nse_engine")

# Configuration
NTFY_TOPIC = "nse_scalper_signals"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

def send_alert(message, tags=None):
    try:
        requests.post(NTFY_URL, data=message.encode('utf-8'), headers={"Tags": tags or ""})
        logger.info(f"Alert sent: {message}")
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")

def check_stock(sym, rvol_thresh=2.0, min_sqz=5):
    try:
        # 1. Get Intraday 5m Bars
        bars = get_intraday_bars(sym, interval="5m", range="1d")
        if bars.empty or len(bars) < 20: return
        
        # 2. Calculate Technicals
        bars['ema50'] = bars['close'].ewm(span=50, adjust=False).mean()
        bars['vwap'] = calc_vwap(bars)
        bars['val'], bars['sqzOn'] = squeeze_momentum(bars)
        bars['rvol'] = rvol(bars)
        
        # Squeeze duration
        bars['sqz_len'] = bars['sqzOn'].astype(int).groupby(bars['sqzOn'].astype(int).diff().ne(0).cumsum()).cumsum()
        
        last = bars.iloc[-1]
        prev = bars.iloc[-2]
        
        # 3. High-Win-Rate Signal Logic (58.7% WR)
        # Time Window Filter: 10:00 AM - 2:30 PM IST
        if not (10 <= last['time'].hour <= 14): return
        
        is_long = last['close'] > last['ema50'] and last['close'] > last['vwap'] and last['val'] > 0 and prev['val'] <= 0
        is_short = last['close'] < last['ema50'] and last['close'] < last['vwap'] and last['val'] < 0 and prev['val'] >= 0
        
        if (is_long or is_short) and last['rvol'] >= rvol_thresh and prev['sqz_len'] >= min_sqz:
            side = "🚀 BUY" if is_long else "🚨 SELL"
            tp = last['close'] + last['atr'] * 1.5 if is_long else last['close'] - last['atr'] * 1.5
            sl = last['close'] - last['atr'] * 2.0 if is_long else last['close'] + last['atr'] * 2.0
            msg = f"{side} SETUP: {sym}\nPrice: {last['close']:.2f}\nTarget: {tp:.2f}\nStop: {sl:.2f}\nLogic: 58% WR Scalp"
            send_alert(msg, tags="fire,chart_with_upwards_trend" if is_long else "warning,chart_with_downwards_trend")

    except Exception as e:
        logger.error(f"Error checking {sym}: {e}")

def get_top_movers():
    logger.info("Refreshing Top 10 Gainers and Losers...")
    quotes = fetch_live_quotes(FO_STOCKS)
    if quotes.empty: return FO_STOCKS[:20]
    
    quotes['change'] = (quotes['price'] - quotes['open']) / quotes['open']
    sorted_q = quotes.sort_values('change')
    top_losers = sorted_q.head(10)['symbol'].tolist()
    top_gainers = sorted_q.tail(10)['symbol'].tolist()
    return list(set(top_gainers + top_losers))

def main():
    logger.info("Starting NSE Live Signal Engine (Golden Momentum Focus)...")
    send_alert("NSE Scalper Engine Started. Monitoring Top Movers with Golden Settings.", tags="rocket")
    
    last_refresh = 0
    targets = []
    
    while True:
        if time.time() - last_refresh > 900:
            targets = get_top_movers()
            last_refresh = time.time()
            logger.info(f"Monitoring Targets: {', '.join(targets)}")
        
        for sym in targets:
            check_stock(sym)
            time.sleep(1)
        
        time.sleep(60)

if __name__ == "__main__":
    main()
