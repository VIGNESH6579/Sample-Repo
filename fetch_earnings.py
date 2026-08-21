"""
fetch_earnings.py — Collect latest quarterly result periods for the most
liquid F&O stocks from Screener.in (free, public).

Stores data/earnings_dates.csv: symbol,quarter_end
Slugs corrected for known Screener naming; retries with backoff.
"""
import time
import re
import sys
import logging
import requests
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")

log = logging.getLogger("nse_scalper.earnings")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"}

# Most liquid ~55 F&O stocks (avg 5m volume gate used in backtest passes these)
FO_LIQUID = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC",
    "LT", "AXISBANK", "BAJFINANCE", "MARUTI", "SUNPHARMA", "TATASTEEL", "ULTRACEMCO",
    "HINDUNILVR", "KOTAKBANK", "WIPRO", "ONGC", "NTPC", "ADANIENT", "ADANIPORTS",
    "JSWSTEEL", "BAJAJFINSV", "BAJAJ-AUTO", "HEROMOTOCO", "CIPLA", "DRREDDY", "NESTLEIND",
    "BRITANNIA", "ASIANPAINT", "EICHERMOT", "GRASIM", "TECHM", "HCLTECH", "TITAN",
    "GAIL", "BPCL", "IOC", "HINDALCO", "VEDL", "YESBANK", "PNB", "BANKBARODA", "CANBK",
    "IDFCFIRSTB", "FEDERALBNK", "IRCTC", "INDIGO", "ZEEL", "LUPIN", "M&M", "MUTHOOTFIN",
    "PFC", "RECLTD", "SBICARD", "SIEMENS", "PIIND", "POLYCAB", "TORNTPHARM", "TVSMOTOR",
    "HAVELLS", "DABUR", "GODREJCP", "MARICO", "DIXON", "HAL", "BEL", "SHRIRAMFIN",
    "MRF", "PAGEIND", "ABB", "AMBUJACEM", "DABUR", "BHEL", "IRFC", "RVNL", "SJVN",
    "SUZLON", "ZOMATO", "TRENT", "DMART", "APOLLOHOSP", "MAXHEALTH", "AUROPHARMA",
    "ZYDUSLIFE", "BOSCHLTD", "LTIM", "MOTILALOFS", "NAUKRI", "COFORGE", "PERSISTENT",
    "TATACONSUM", "TATAPOWER", "VOLTAS", "TVT", "SYNGENE",
]

_SLUG = {
    "M&M": "M&M", "BAJAJ-AUTO": "BAJAJ-AUTO", "BAJAJFINSV": "BAJAJFINSV",
    "BAJFINANCE": "BAJFINANCE",
}


def fetch_one(s, sess):
    slug = _SLUG.get(s, s.lower())
    for attempt in range(3):
        try:
            r = sess.get(f"https://www.screener.in/company/{slug}/consolidated/",
                         headers=_HEADERS, timeout=35)
            if r.status_code != 200:
                time.sleep(4 * (attempt + 1))
                continue
            keys = re.findall(r'data-date-key="(\d{4}-\d{2}-\d{2})"', r.text)
            real = [k for k in keys if not k.startswith("TTM")]
            if real:
                return s, max(real)
            return s, None
        except Exception as e:
            log.warning("%s attempt %d: %s", s, attempt, e)
            time.sleep(5)
    return s, None


def main():
    sess = requests.Session()
    rows = []
    for s in FO_LIQUID:
        sym, qe = fetch_one(s, sess)
        if qe:
            rows.append((sym, qe))
        time.sleep(1.2)
    df = pd.DataFrame(rows, columns=["symbol", "quarter_end"])
    df.to_csv("/home/ubuntu/nse_scalper/data/earnings_dates.csv", index=False)
    print(f"collected {len(df)}/{len(FO_LIQUID)}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
