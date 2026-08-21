"""
build_news_history.py — Collect a rolling archive of RSS headlines to a local
SQLite DB, so the backtest has genuine historical news timestamps.

Run periodically (cron): headlines are append-only with source + pub time.
For the initial backtest we also backfill from Google News archive via
rss-bridge-free methods is not possible; instead we use a pragmatic approach:
fetch headlines now (forward archive) AND for backtest use historically
re-published "top news of the day" style articles is unreliable.

Therefore the backtest uses a two-layer design:
  Layer 1 (news trigger layer, forward-only): live RSS detection
  Layer 2 (price-behavior layer, historical): "news-day momentum" proxy —
    on days with large early-move + high relative volume, we assume a news
    catalyst and test whether momentum continuation scalps were profitable.

This script is the live-layer archive; it starts collecting immediately.
"""
import sqlite3
import sys
import logging

sys.path.insert(0, "/home/ubuntu/nse_scalper")
from modules.news import fetch_all, STOCK_KEYWORDS

DB = "/home/ubuntu/nse_scalper/news_archive.db"
log = logging.getLogger("nse_scalper.archive")


def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS headlines (
        hash TEXT PRIMARY KEY,
        title TEXT,
        source TEXT,
        link TEXT,
        pub_time TEXT,
        inserted TEXT)""")
    conn.commit()
    return conn


def collect():
    conn = init_db()
    items = fetch_all()
    added = 0
    for it in items:
        h = f"{it['source']}:{it['title'].lower().strip()}"[:64]
        try:
            conn.execute("INSERT OR IGNORE INTO headlines VALUES (?,?,?,?,?,?)",
                         (h, it["title"], it["source"], it["link"],
                          it["time"].isoformat(), it["time"].now().isoformat()))
            if conn.total_changes:
                added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    log.info("collected %d headlines, archive size: %d", added, added)
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    items = collect()
    print(f"Fetched {len(items)} headlines today")
    for sym in ["RELIANCE", "TCS", "HDFCBANK", "ZOMATO"]:
        from modules.news import headlines_for_stock
        m = headlines_for_stock(sym, items, max_age_min=1440)
        print(f"  {sym}: {len(m)} headlines in last 24h")
