# Simple Logic

Simple Logic is an alert-only NSE F&O option scalp monitor. It evaluates the supplied F&O stock universe, excludes LTIMindtree, and sends an ntfy notification whenever a stock satisfies the CALL or PUT entry conditions. It does not place orders.

## Signal behavior

The service checks the 09:30–11:30 IST entry window. A CALL candidate requires LTP above VWAP and day high, call OI change below -4%, call spread below 1.5, and volume above 1.5 times average volume. A PUT candidate uses the mirrored conditions below VWAP and day low. The service evaluates all qualifying stocks; there is no one-signal-per-day limit and no top-one restriction. It suppresses a duplicate while the same symbol-side position remains active, then permits a new alert after that position exits.

Exits are generated at premium +40%, premium -25%, 45 minutes after entry, or when the underlying breaks the relevant day-high/day-low confirmation.

## Data and notifications

The data layer is isolated in `tradingview_adapter.py` and normalizes TradingView scanner fields into the strategy engine. Because field availability can vary by exchange feed, the deployment must expose the OI, spread, and ATM-premium fields used by the rules; if those fields are unavailable, the service will not fabricate a signal. ntfy publishing uses `NTFY_TOPIC` and optionally `NTFY_TOKEN`.

## Local run

```bash
pip install -r requirements.txt
python app.py
```

Open `/` for the dashboard and `/health` for UptimeRobot. The service reads the Render-provided `PORT` variable.

## Render configuration

Create a free Python web service from this repository or deploy the included `render.yaml`. Set `NTFY_TOPIC` to a private, hard-to-guess ntfy topic. Set `NTFY_TOKEN` only when using an authenticated ntfy server. `TRADINGVIEW_SCANNER_URL` defaults to the India scanner endpoint and can be overridden if the authorized feed uses a different endpoint.

The application is intentionally alert-only. Before relying on any alert for a live trade, validate the normalized TradingView fields and contract mapping in the dashboard logs.

## Disclaimer

This tool is for research and alerting only. It is not investment advice, and it does not place orders. Verify every alert independently before acting.
