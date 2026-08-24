# Simple Logic

Simple Logic is an alert-only NSE F&O option scalp monitor. It uses the supplied `NSE_FO_Options_Stocks_List.xlsx` as its universe, maps every non-LTIM company to an NSE/Angel One symbol, and uses live Angel One SmartAPI responses at runtime. The verified universe contains **207 stocks after excluding LTIMindtree**. The application does not place orders.

## Live monitoring behavior

The service polls TradingView during market hours and rejects incomplete rows instead of substituting hard-coded prices. It reads each stock’s live LTP, VWAP, current session high and low, volume, and a historical daily average-volume baseline. The current session high and low are evaluated per stock, not shared across the universe. The option OI, spread, and ATM-premium fields must also be present in the configured live feed before a signal can be produced.

The entry window is 09:30–15:20 IST. A CALL candidate requires LTP above VWAP and at or above the stock’s current-session high, call OI change below -4%, call spread below 1.5, and volume above 1.5 times average volume. A PUT candidate uses the mirrored conditions below VWAP and at or below the stock’s current-session low. Every qualifying stock can generate a signal; there is no one-signal-per-day limit. Duplicate unchanged setups are suppressed while the same symbol-side position is active.

Exits are generated at option premium +40%, option premium -25%, 45 minutes after entry, or when the underlying breaks the relevant stock-specific day-high/day-low confirmation.

## Scheduled notifications

At or after **09:15 IST**, the service sends one day-start notification per date showing the live provider and universe count. At or after **15:20 IST**, it sends one EOD report per date with entry count, entry symbols, exit count, exit reasons, and open positions. The service must be awake around those times; UptimeRobot can keep the public Render endpoint active. If the service starts after a scheduled minute, it sends the report on its first cycle after that time rather than inventing a missed timestamp.

## Deployment

The public dashboard is available at `https://simple-logic.onrender.com/`, and the UptimeRobot target is `https://simple-logic.onrender.com/health`. Configure `TELEGRAM_BOT_TOKEN` with the BotFather token and `TELEGRAM_CHAT_ID` with the destination chat ID. Telegram sends day-start, entry, exit, and EOD notifications through the Bot API. Angel One credentials are configured through `ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PASSWORD`, and `ANGEL_TOTP_SECRET`. The adapter uses a session-start OI baseline and a historical daily volume baseline; it fails closed when required live fields are unavailable.

## Local run

```bash
pip install -r requirements.txt
python app.py
```

The `/` route provides the dashboard, `/health` is the uptime target, and `/api/status` exposes runtime status. `run_tests.py` checks the deterministic strategy logic. `verify_live_coverage.py` checks mapped ticker coverage; `/api/diagnose/<symbol>` reports the live pass/fail conditions for one symbol.

## Disclaimer

This tool is for research and alerting only. It is not investment advice, and it does not place orders. Verify every alert independently before acting.
