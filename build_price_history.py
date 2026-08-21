"""
build_price_history.py — Download historical intraday bars for all F&O stocks
from Yahoo Finance (free) for the backtest.

Yahoo interval=5m range=60d limit -> ~60 days of 5-minute data per stock.
Stored as per-stock CSV in data/hist/.
"""
import os
import time
import sys
import logging
import concurrent.futures as cf

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from modules.nse_data import FO_STOCKS, get_intraday_bars, ticker_of

OUT = "/home/ubuntu/nse_scalper/data/hist"
log = logging.getLogger("nse_scalper.history")


def fetch_one(sym):
    path = os.path.join(OUT, f"{sym}.csv")
    if os.path.exists(path) and os.path.getsize(path) > 500:
        return sym, "cached"
    df = get_intraday_bars(sym, "5m", "60d")
    if len(df) < 50:
        return sym, f"thin({len(df)})"
    df.to_csv(path)
    return sym, f"ok({len(df)})"


def main():
    os.makedirs(OUT, exist_ok=True)
    ok, thin, fail = 0, 0, 0
    results = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(fetch_one, s) for s in FO_STOCKS]
        for fut in cf.as_completed(futs):
            sym, status = fut.result()
            results.append((sym, status))
            if status.startswith("ok"):
                ok += 1
            elif status.startswith("thin"):
                thin += 1
            else:
                fail += 1
            time.sleep(0.2)
    print(f"done: ok={ok} thin={thin} fail={fail} total={len(FO_STOCKS)}")
    for sym, status in sorted(results):
        if not status.startswith("ok"):
            print(" ", sym, status)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
