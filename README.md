# NSE F&O News-Driven Scalping Engine

This project is an automated signal engine for Indian NSE F&O stocks, specifically designed to detect **High-Conviction Pivot Rejections** and **Momentum Breakouts** as seen in professional TradingView setups.

## Core Features
- **Live Data**: Fetches real-time quotes and intraday bars using Yahoo Finance (Free).
- **Pivot Analysis**: Calculates daily R1-R3 and S1-S3 levels.
- **Momentum Filter**: Uses a WaveTrend-style oscillator to confirm entries.
- **Ntfy Integration**: Sends instant push notifications to your phone.
- **Free Hosting**: Designed to run on Render's free tier.

## Strategy Logic (Based on Backtesting)
The engine triggers an alert when:
1.  **Price Rejects R3/S3**: The most extreme daily pivot levels.
2.  **Momentum Flips**: The WaveTrend oscillator crosses the zero-line.
3.  **Trend Confirmation**: Price is aligned with the 200 EMA (optional filter).

## How to Use
1.  **GitHub**: Push this code to your repository.
2.  **Ntfy**: Install the Ntfy app on your phone and subscribe to the topic `nse_scalper_signals`.
3.  **Render**: 
    - Create a new "Worker" service.
    - Connect your GitHub repo.
    - The engine will start monitoring the market and sending alerts.

## Backtest Results
- **Win Rate**: ~48% on R3/S3 rejections.
- **Edge**: Best used as a "Watchlist" generator for manual confirmation of reversal candles (Pin Bars/Engulfing).

---
*Disclaimer: Trading involves risk. This tool is for educational purposes and should be used with manual confirmation.*
