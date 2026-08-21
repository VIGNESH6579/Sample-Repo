"""
news.py — Free multi-source news aggregation for market-relevant headlines.

Sources (all free RSS, verified working 2026-08):
  - Moneycontrol Business
  - Economic Times Markets
  - Livemint Markets
  - Business Standard Markets
  - Google News (India business search)

Returns deduplicated headlines with source + publish time.
"""
import logging
import time
import hashlib
import re
import requests
import feedparser
from datetime import datetime, timezone, timedelta

log = logging.getLogger("nse_scalper.news")

IST = timezone(timedelta(hours=5, minutes=30))

FEEDS = {
    "moneycontrol": "https://www.moneycontrol.com/rss/business.xml",
    "economictimes": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "livemint": "https://www.livemint.com/rss/markets",
    "businessstandard": "https://www.business-standard.com/rss/markets-106.rss",
    "googlenews": "https://news.google.com/rss/search?q=india+stock+market+OR+india+business&hl=en-IN&gl=IN&ceid=IN:en",
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"}

# Keywords that map headlines to F&O stock tickers (extended manually over time)
STOCK_KEYWORDS = {
    "RELIANCE": ["reliance", "ril "],
    "TCS": ["tcs ", "tata consultancy"],
    "INFY": ["infosys"],
    "HDFCBANK": ["hdfc bank", "hdfcbank"],
    "ICICIBANK": ["icici bank", "icicibank"],
    "SBIN": ["sbi ", "state bank"],
    "BHARTIARTL": ["airtel", "bharti"],
    "ITC": ["itc "],
    "LT": ["larsen", " l&t ", "l and t", "larSEN"],
    "AXISBANK": ["axis bank"],
    "BAJFINANCE": ["bajaj finance"],
    "MARUTI": ["maruti", "suzuki"],
    "SUNPHARMA": ["sun pharma"],
    "TATAMOTORS": ["tata motors", "jaguar land"],
    "TATASTEEL": ["tata steel"],
    "ULTRACEMCO": ["ultratech", "ultra cement"],
    "HINDUNILVR": ["hindustan unilever", "hul "],
    "KOTAKBANK": ["kotak"],
    "WIPRO": ["wipro"],
    "ONGC": ["ongc"],
    "NTPC": ["ntpc"],
    "POWERGRID": ["power grid"],
    "COALINDIA": ["coal india"],
    "ADANIENT": ["adani enter", "adani enterprises"],
    "ADANIPORTS": ["adani port"],
    "JSWSTEEL": ["jsw steel"],
    "BAJAJFINSV": ["bajaj finserv"],
    "BAJAJ-AUTO": ["bajaj auto"],
    "HEROMOTOCO": ["hero moto", "hero motocorp"],
    "DIVISLAB": ["divi", "divi's"],
    "CIPLA": ["cipla"],
    "DRREDDY": ["dr reddy", "drreddy"],
    "NESTLEIND": ["nestle"],
    "BRITANNIA": ["britannia"],
    "ASIANPAINT": ["asian paint"],
    "EICHERMOT": ["eicher", "royal enfield"],
    "GRASIM": ["grasim"],
    "TECHM": ["tech mahindra"],
    "HCLTECH": ["hcl tech", "hcl technologies"],
    "TITAN": ["titan company", "titan co"],
    "GAIL": ["gail"],
    "BPCL": ["bharat petroleum"],
    "IOC": ["indian oil"],
    "HINDALCO": ["hindalco"],
    "VEDL": ["vedanta"],
    "YESBANK": ["yes bank"],
    "PNB": ["punjab national bank", "pnb "],
    "BANKBARODA": ["bank of baroda"],
    "CANBK": ["canara bank"],
    "IDFCFIRSTB": ["idfc first"],
    "FEDERALBNK": ["federal bank"],
    "IRCTC": ["irctc"],
    "INDIGO": ["indiGo", "interglobe"],
    "ZEEL": ["zee ", "zee entertainment"],
    "LUPIN": ["lupin"],
    "M&M": ["mahindra ", "mahindra & mahindra"],
    "MUTHOOTFIN": ["muthoot"],
    "PFC": ["power finance"],
    "RECLTD": ["rec limited", "rural electrification"],
    "SBICARD": ["sbi card"],
    "SIEMENS": ["siemens"],
    "PIIND": ["pi industries"],
    "POLYCAB": ["polycab"],
    "TORNTPHARM": ["torrent pharma"],
    "TVSMOTOR": ["tvs motor"],
    "HAVELLS": ["havells"],
    "BERGERPAINT": ["berger paint"],
    "DABUR": ["dabur"],
    "GODREJCP": ["godrej consumer", "godrej cp"],
    "MARICO": ["marico"],
    "DIXON": ["dixon"],
    "HAL": ["hal ", "hindustan aeronautics"],
    "BEL": ["bharat electronics", " bel "],
    "MOTILALOFS": ["motilal oswal"],
    "NAUKRI": ["info edge", "naukri"],
    "COFORGE": ["coforge"],
    "PERSISTENT": ["persistent"],
    "LTIM": ["ltimindtree"],
    "TATACONSUM": ["tata consumer"],
    "TATAPOWER": ["tata power"],
    "VOLTAS": ["voltas"],
    "TRENT": ["trent ", "westside"],
    "DMART": ["dmart", "avenue supermarket"],
    "APOLLOHOSP": ["apollo hospital"],
    "MAXHEALTH": ["max healthcare"],
    "AUROPHARMA": ["aurobindo"],
    "ZYDUSLIFE": ["zydus"],
    "BOSCHLTD": ["bosch"],
    "SHRIRAMFIN": ["shriram finance"],
    "MRF": ["mrf "],
    "PAGEIND": ["page industries", "jockey"],
    "ABB": ["abb "],
    "AMBUJACEM": ["ambuja cement"],
    "DABUR_IND": ["dabur"],
    "BHEL": ["bhel"],
    "IRFC": ["irfc"],
    "RVNL": ["rvnl", "rail vikas"],
    "IRCON": ["ircon"],
    "SJVN": ["sjvn"],
    "HUDCO": ["hudco"],
    "SUZLON": ["suzlon"],
    "ZOMATO": ["zomato", "blinkit"],
    "PAYTM": ["paytm", "one97"],
    "NYKAA": ["nykaa"],
    "DELHIVERY": ["delhivery"],
    "PBAINFRA": ["pba infra"],
    "CDSL": ["cdsl"],
    "IEX": ["indian energy exchange"],
    "MAZDOCK": ["mazagon"],
    "LICI": ["lic ", "life insurance corporation"],
}


def _pub_time(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        tp = getattr(entry, attr, None)
        if tp:
            try:
                return datetime(*tp[:6], tzinfo=IST)
            except Exception:
                pass
    return datetime.now(IST)


def fetch_all() -> list[dict]:
    """Fetch all feeds, dedupe by headline hash. Returns list of
    {title, source, link, time} newest first."""
    items = []
    seen = set()
    for source, url in FEEDS.items():
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            if r.status_code != 200:
                log.warning("feed %s http %s", source, r.status_code)
                continue
            feed = feedparser.parse(r.content)
            for e in feed.entries[:40]:
                title = (e.get("title") or "").strip()
                if not title:
                    continue
                h = hashlib.md5(title.lower().encode()).hexdigest()[:10]
                if h in seen:
                    continue
                seen.add(h)
                items.append({
                    "title": re.sub(r"\s+", " ", title),
                    "source": source,
                    "link": e.get("link", ""),
                    "time": _pub_time(e),
                })
        except Exception as ex:
            log.warning("feed %s error: %s", source, ex)
        time.sleep(0.5)
    items.sort(key=lambda x: x["time"], reverse=True)
    return items


def headlines_for_stock(symbol: str, items: list[dict], max_age_min: int = 60) -> list[dict]:
    """Return headlines mentioning the given stock within the age window."""
    now = datetime.now(IST)
    cutoff = now - timedelta(minutes=max_age_min)
    kw = STOCK_KEYWORDS.get(symbol, [symbol.lower()])
    out = []
    for it in items:
        if it["time"] < cutoff:
            continue
        low = it["title"].lower()
        if any(k in low for k in kw):
            out.append(it)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    items = fetch_all()
    print(f"total headlines: {len(items)}")
    for it in items[:15]:
        print(f"[{it['source']}] {it['time'].strftime('%H:%M')} {it['title'][:90]}")
    for sym in ["RELIANCE", "TCS", "ZOMATO"]:
        m = headlines_for_stock(sym, items, max_age_min=1440)
        print(f"\n{sym}: {len(m)} recent headlines")
        for it in m[:3]:
            print(f"   {it['time'].strftime('%H:%M')} {it['title'][:90]}")
