# Project state — NSE F&O news-driven scalping system (as of Aug 20, 2026)

## User requirements (from messages)
- Intraday, stock-specific option scalping signals for ALL NSE F&O stocks
- Live data from NSE website OR TradingView; news source my choice, free
- Signals pushed to NTFY (user will provide ntfy topic)
- User has Render + GitHub access; entire project must be fully free
- Logic must be backtested iteratively until results are statistically satisfying
- User wants Pine Script v6 (delivered earlier: /home/ubuntu/perfect_indicator_v1.pine)

## Data sources verified (Phase 1)
- nseindia.com: BLOCKED (Akamai 403) from Python AND sandbox browser (captcha)
- Yahoo Finance chart API: WORKS — https://query1.finance.yahoo.com/v8/finance/chart/{SYM}.NS
  with params interval/range; free, no key; gives live price + 5m intraday bars
- News RSS feeds WORKING: moneycontrol business.xml, ET markets .cms, livemint /rss/markets,
  business-standard markets-106.rss, Google News IN rss search
- Option premiums NOT available free → use Black-Scholes synthetic ATM premium proxy
  (IV = 0.6*short RV + 0.4*long RV) in modules/options.py — works, tested

## Repo structure built (in /home/ubuntu/nse_scalper/)
- modules/nse_data.py — quotes, intraday bars, FO_STOCKS list (185 symbols; fixed LTM,
  SYNGENE, removed delisted TATAMOTORS/SYNGM/LTIM; ticker_of adds .NS)
- modules/news.py — fetch_all() 5 feeds, STOCK_KEYWORDS dict mapping tickers to keywords,
  headlines_for_stock(symbol, items, max_age_min)
- modules/options.py — atm_strike, bs_price, bs_delta, realized_vol, synthetic_atm_premium
- build_news_history.py — appends headlines to news_archive.db (SQLite, live archive)
- build_price_history.py — downloads 60d 5m bars per stock to data/hist/{SYM}.csv (183 OK)
- backtest_news_scalp.py (iter1), backtest_iter2.py, backtest_iter3.py — results in
  docs/iteration_log.md (all losing so far: PF 0.39 / 0.26 / 0.41)
- docs/iteration_log.md, docs/project_state.md (this file)

## Backtest environment facts
- Yahoo intraday: interval=5m range=60d works; 1m unavailable
- ~390 min session; market time Asia/Kolkata
- Costs model: 0.10% round trip options; delta proxy 0.6 ATM

## Next steps (Phase 3 continuing)
- Iteration 4: pullback-after-impulse entry logic (higher-low after spike),
  liquidity filter (avg volume), trend alignment; expect PF > 1.3
- Then assemble: live signal engine (engine.py), ntfy.py, app.py FastAPI/Flask
  for Render cron, render.yaml, requirements.txt, Procfile
- GitHub repo: VIGNESH6579/Sample-Repo already connected; ask user before pushing
  or create new repo nse-news-scalper (--private default)
- Ntfy: https://ntfy.sh/{topic}; POST with Basic auth optional; free
