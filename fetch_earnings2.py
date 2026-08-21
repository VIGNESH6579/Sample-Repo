"""
fetch_earnings2.py — Robust version: per-request timeout (15s),
saves incrementally to CSV after each stock, skips already fetched.
"""
import os
import re
import sys
import time
import logging
import requests
import pandas as pd

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from fetch_earnings import FO_LIQUID, _HEADERS

log = logging.getLogger("nse_scalper.earnings")
OUT = "/home/ubuntu/nse_scalper/data/earnings_dates.csv"


def quarter_end_for(s, sess):
    r = sess.get(f"https://www.screener.in/company/{s}/consolidated/",
                 headers=_HEADERS, timeout=15)
    if r.status_code != 200:
        return None
    keys = re.findall(r'data-date-key="(\d{4}-\d{2}-\d{2})"', r.text)
    real = [k for k in keys if not k.startswith("TTM")]
    return max(real) if real else None


def main():
    sess = requests.Session()
    existing = {}
    if os.path.exists(OUT):
        try:
            df0 = pd.read_csv(OUT)
            existing = dict(zip(df0["symbol"], df0["quarter_end"]))
        except Exception:
            pass
    rows = dict(existing)
    remaining = [s for s in FO_LIQUID if s not in rows]
    print(f"fetching {len(remaining)} stocks")
    for i, s in enumerate(remaining):
        try:
            qe = quarter_end_for(s, sess)
            if qe:
                rows[s] = qe
            elif i % 10 == 0:
                log.warning("%s: no data", s)
        except Exception as e:
            log.warning("%s: %s", s, e)
        if (i + 1) % 5 == 0 or i == len(remaining) - 1:
            pd.DataFrame(list(rows.items()), columns=["symbol", "quarter_end"]).to_csv(OUT, index=False)
            print(f"{i+1}/{len(remaining)} done, {len(rows)} with data", flush=True)
        time.sleep(1.0)
    print(f"total with data: {len(rows)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
