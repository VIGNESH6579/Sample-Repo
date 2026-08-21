# Data Source Verification (Phase 1)

## NSE direct (nseindia.com)
- Blocked by Akamai (403) from both Python requests and curl_cffi impersonation — confirmed dead for server-side use from outside India data centers.
- Browser also hit captcha wall. NOT usable for the automated project.

## Yahoo Finance (query1.finance.yahoo.com)
- WORKS: /v8/finance/chart/{SYM}.NS with interval/range returns live intraday quotes (5m bars, last traded price, timestamp) for NSE F&O stocks. RELIANCE.NS returned price 1313.2 with current timestamp.
- Free, no key needed. Rate-limits exist but sufficient for periodic polling (per-stock polling at ~5-min cadence is fine).
- Provides: spot price, OHLCV intraday bars, prev close, 52wk range, currency, exchange delay status.
- Limitation: no option chain (no option premiums). So option-chain scalping must proxy option behavior via spot momentum + synthetic premium proxy OR use a secondary source.

## Sensibull
- Option chain page renders client-side; internal API endpoints return HTML for unauthorized calls. No anonymous programmatic access confirmed. Not usable.

## Strategy decision
- Spot/intraday momentum + news → free via Yahoo Finance (NSE tickers .NS) + NSE F&O list (static list from nseindia site once + maintained; or use Yahoo list).
- Option-chain signals: use the "spot-to-option" mapping: ATM strike = round(spot/10)*10 etc. Option premium proxy = Black-Scholes approximation using Yahoo IV unavailable → use ATM option premium proxy formula (BSM with IV proxied by 30-day HV from 5m bars). This keeps it 100% free.
- News: free RSS sources — NSE India RSS feed (200 OK, 306KB), Moneycontrol, Economic Times (verify), Livemint RSS. Multiple sources for redundancy.

## Next: verify RSS feeds for market-relevant news with timestamps.
