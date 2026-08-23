# Simple Logic

Simple Logic is an alert-only NSE F&O option scalp monitor. It uses the supplied `NSE_FO_Options_Stocks_List.xlsx` as its universe, maps every non-LTIM company to an NSE/TradingView symbol, and uses live TradingView scanner responses at runtime. The verified universe contains **207 stocks after excluding LTIMindtree**. The application does not place orders.

## Live monitoring behavior

The service polls TradingView during market hours and rejects incomplete rows instead of substituting hard-coded prices. It reads each stock’s live LTP, VWAP, current session high and low, volume, and average volume. The current session high and low are evaluated per stock, not shared across the universe. The option OI, spread, and ATM-premium fields must also be present in the configured live feed before a signal can be produced.

The entry window is 09:30–11:30 IST. A CALL candidate requires LTP above VWAP and the stock’s current day high, call OI change below -4%, call spread below 1.5, and volume above 1.5 times average volume. A PUT candidate uses the mirrored conditions below VWAP and the stock’s current day low. Every qualifying stock can generate a signal; there is no one-signal-per-day limit. Duplicate unchanged setups are suppressed while the same symbol-side position is active.

Exits are generated at option premium +40%, option premium -25%, 45 minutes after entry, or when the underlying breaks the relevant stock-specific day-high/day-low confirmation.

## Scheduled notifications

At or after **09:15 IST**, the service sends one day-start notification per date showing the live provider and universe count. At or after **15:40 IST**, it sends one EOD report per date with entry count, entry symbols, exit count, exit reasons, and open positions. The service must be awake around those times; UptimeRobot can keep the public Render endpoint active. If the service starts after a scheduled minute, it sends the report on its first cycle after that time rather than inventing a missed timestamp.

## Deployment

The public dashboard is available at `https://simple-logic.onrender.com/`, and the UptimeRobot target is `https://simple-logic.onrender.com/health`. Configure `NTFY_TOPIC` to a private, hard-to-guess ntfy topic and optionally configure `NTFY_TOKEN` for authenticated publishing. `TRADINGVIEW_SCANNER_URL` defaults to `https://scanner.tradingview.com/india/scan`.

## Local run

```bash
pip install -r requirements.txt
python app.py
```

The `/` route provides the dashboard, `/health` is the uptime target, and `/api/status` exposes runtime status. `run_tests.py` checks the deterministic strategy logic. `verify_live_coverage.py` checks that all 207 mapped tickers return live TradingView rows.

## Disclaimer

This tool is for research and alerting only. It is not investment advice, and it does not place orders. Verify every alert independently before acting.
