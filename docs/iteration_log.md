# Iteration log — news-driven F&O scalp backtest

Data: 183 NSE F&O stocks, ~60 days of 5m bars via Yahoo Finance (free),
Jun 2 – Aug 20, 2026. Costs 0.10% RT, ATM delta proxy 0.6.

## Iteration 1 — raw breakout + RVOL 1.8
4601 trades, WR 37.7%, PF 0.39. Diagnosis: losers concentrated in
low-liquidity/volatile stocks; no quality filters; too many trades/day.

## Iteration 2 — 1 trade/day, strength + trend + regime filters, RVOL 2.2, TP=SL=1ATR
2073 trades, WR 41.9%, PF 0.26. Diagnosis: TP exit avg +0.08% vs SL -0.28%;
asymmetry killed it. Time-stop exits at breakeven-ish.

## Iteration 3 — asymmetric TP 2ATR/SL 1ATR + breakeven rule
1866 trades, WR 27.7%, PF 0.41. Diagnosis: breakouts failing 72% of time
(20-bar high breakouts in noisy regime are mean-reversion traps).
Winners when they hit average +0.24% but too rare.

## Key insight emerging
Momentum breakouts are NOT the right trigger for a NEWS strategy. News
events (results, orders, management changes) typically cause an IMPULSE then
a continuation OR a fade. The profitable pattern in Indian F&O is:
  - Opening-range momentum continuation WITH trend alignment on higher TF
  - OR post-impulse pullback entry (buy the first higher-low after news spike)
Next iteration: pullback-after-spike entry (the "non-aggressive entry" pattern
the original reel trader described) + stronger regime filter + selective stock
universe (only stocks with genuine news flow, high liquidity).

## Iteration 4 — pullback-after-impulse, strict (RVOL 2.5, range 1.5x, 1 trade/day)
12 trades, PF 0.73. Too few trades; gate too strict; per-day cap hurt.

## Iteration 5 — relaxed gate (RVOL 2.0, range 1.2x), 2 trades/day
21 trades, PF 0.56. Better but still volume-filter bug (500k per-day vs 5m bars).

## Iteration 6 — fixed volume gate (avg 5m bar vol > 20k), no day cap
1105 trades, 88 stocks, WR 38.2%, PF 0.38. Losers: SL -0.24% avg, TIME STOP
-0.31% avg (worse than SL!). Winners +0.15%. Only 8.6% profitable days.

## Core structural finding (important honesty note)
Time-stop exits are the biggest bleed: pullbacks that don't reach TP within
18 bars drift down and exit -0.31%. The pattern itself is marginal because:
(a) Yahoo 5m data lacks order-flow; (b) A news-replay backtest on 60 days
cannot statistically validate a news strategy; (c) retail options scalping in
India has negative expectancy after costs in general (SEBI: 88% retail F&O
loss FY26 — consistent with our findings).

## Pivot for iteration 7+ (must be honest with user too)
Instead of forcing profitability, restructure to what is known to work:
  1. Mean-reversion scalp ON the impulse: fade overextended spikes back to
     VWAP with tight SL — but this fights news direction.
  2. Trend continuation with TIME-ALIGNED exits: enter pullback, exit at fixed
     time window OR at first sign of weakness (close < entry bar low) instead
     of fixed ATR TP -> removes the time-stop bleed.
  3. Use close-below-SMA20 early exit instead of time stop.
  4. Only trade stocks that actually got news (keyword match) — in live system
     this halves false triggers; in backtest, proxy via RVOL 2.5+.

## Iteration 7 — structure exits (weak/trend) replace time stop, RVOL 2.5
555 trades, PF 0.35. Trend-exit bleed: -0.25% avg. Still losing.

## Iteration 8 — wide SL (min 2 ATR), trend exit on SMA20, day-must-be-up filter
549 trades, PF 0.41. Trend exits still -0.39%. Consistent result across
6 distinct logic families: PF 0.26–0.73, all < 1.

## FINAL HONEST CONCLUSION (must tell user)
After 8 iterations across ~5,500+ total trades on 88-183 liquid NSE F&O
stocks over 60 days of real 5-minute data with realistic option costs:
NO configuration of the news-impulse continuation scalp is profitable.
Best exit-structure combo (iter-7) PF 0.35; most robust (iter-8) PF 0.41.

Why (evidence-based):
 1. 88% of Indian retail F&O traders lose (SEBI FY26 study) — consistent.
 2. The "news impulse continuation" edge is captured by HFT/institutional
    flow within seconds; by the time a 5-minute bar confirms a pullback
    entry, the move's alpha is gone; remaining action is noise + mean reversion.
 3. Options costs (bid-ask + slippage modeled at 0.10% RT) are larger than
    the average edge per scalp (~0.05-0.10% in spot terms).

What IS viable (to build in the live system, transparently):
 - The system can still RUN as an alert/analysis tool: detect news + momentum
   setups, push to Ntfy, let the user decide. Signals marked "watchlist",
   not "trade this".
 - User can add manual confirmation layer (order flow, option chain OI on
   Sensibull free web, time & sales).
 - Alternative edge research directions: opening range breakout on NIFTY
   bank stocks post-news-day, earnings-date strategies (predictable news).
