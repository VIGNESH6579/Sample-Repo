"""
nse_data.py — Free live market data for NSE F&O stocks.

Data backbone: Yahoo Finance public chart API (no API key, no cost).
Tickers: {SYMBOL}.NS on NSE.

Provides:
  - get_quote(symbol): latest price, prev close, day change, volume
  - get_intraday_bars(symbol, interval='5m', range_='5d'): OHLCV intraday
  - F&O stock list (maintained static list, updated from public NSE sources)
"""
import time
import logging
import requests
import pandas as pd

log = logging.getLogger("nse_scalper.data")

_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"}
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)

# NSE F&O stock universe (as of mid-2026, ~190+ symbols). Refresh quarterly.
FO_STOCKS = [
    "AARTIIND", "ABB", "ABBOTINDIA", "ADANIENT", "ADANIPORTS", "ALKEM", "AMBER", "AMBUJACEM",
    "APLAPOLLO", "APOLLOHOSP", "APOLLOTYRE", "ASHOKLEY", "ASIANPAINT", "ASTRAL", "AUROPHARMA",
    "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BALRAMCHIN", "BANDHANBNK", "BANKBARODA",
    "BANKINDIA", "BATAINDIA", "BEL", "BHARATFORG", "BHARTIARTL", "BHEL", "BOSCHLTD", "BPCL",
    "BRITANNIA", "BSOFT", "CAMS", "CANBK", "CANFINHOME", "CHOLAFIN", "CIPLA", "COALINDIA",
    "COFORGE", "COLPAL", "CONCOR", "COROMANDEL", "CUMMINSIND", "DABUR", "DALBHARAT", "DEEPAKNTR", "LTM",
    "DEVYANI", "DIVISLAB", "DIXON", "DLF", "DMART", "DRREDDY", "EICHERMOT", "ESCORTS", "EXIDEIND",
    "FEDERALBNK", "GAIL", "GLENMARK", "GMRAIRPORT", "GODREJCP", "GODREJPROP", "GRASIM", "GUJGASLTD",
    "HAL", "HAVELLS", "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HFCL", "HINDALCO",
    "HINDPETRO", "HINDUNILVR", "HINDZINC", "HUDCO", "ICICIBANK", "ICICIGI", "ICICIPRULI", "IDEA",
    "IDFCFIRSTB", "IEX", "IGL", "INDHOTEL", "INDIAMART", "INDIANB", "INDIGO", "INDUSINDBK",
    "INDUSTOWER", "INFY", "IOC", "IRCTC", "IRFC", "ITC", "JINDALSTEL", "JSWENERGY", "JSWSTEEL",
    "JUBLFOOD", "KALYANKJIL", "KAYNES", "KEI", "LICI", "LT", "LTF", "LTIM", "LUPIN", "M&M",
    "M&MFIN", "MANAPPURAM", "MARICO", "MARUTI", "MAXHEALTH", "MAZDOCK", "MCX", "METROPOLIS",
    "MFSL", "MOTHERSON", "MOTILALOFS", "MPHASIS", "MRF", "MUTHOOTFIN", "NATIONALUM", "NAUKRI",
    "NBCC", "NCC", "NESTLEIND", "NMDC", "NTPC", "OBEROIRLTY", "OFSS", "OIL", "ONGC", "PAGEIND",
    "PATANJALI", "PERSISTENT", "PETRONET", "PFC", "PIDILITIND", "PIIND", "PNB", "POLICYBZR",
    "POLYCAB", "PPLPHARMA", "PRESTIGE", "RBLBANK", "RECLTD", "RELIANCE", "RVNL", "SBICARD",
    "SBILIFE", "SBIN", "SFL", "SHRIRAMFIN", "SIEMENS", "SJVN", "SRF", "SUNPHARMA", "SUPREMEIND",
    "SUZLON", "SYNGM", "TATACONSUM", "TATAELXSI", "TATAPOWER", "TATASTEEL", "TATATECH",
    "TCS", "TECHM", "TIINDIA", "TITAN", "TORNTPHARM", "TORNTPOWER", "TRENT", "TVSMOTOR", "ULTRACEMCO", "SYNGENE",
    "UNIONBANK", "UNITDSPR", "UPL", "VEDL", "VOLTAS", "WIPRO", "YESBANK", "ZEEL", "ZYDUSLIFE",
    "ZYDUSWELL",
]

_cache = {}
_CACHE_TTL = 15  # seconds: Yahoo chart API is ~real-time but avoid hammering


def ticker_of(symbol: str) -> str:
    return f"{symbol}.NS"


def _fetch_chart(symbol: str, interval: str, range_: str):
    key = (symbol, interval, range_)
    now = time.time()
    if key in _cache:
        t, val = _cache[key]
        if now - t < _CACHE_TTL:
            return val
    try:
        r = _SESSION.get(_YAHOO.format(ticker=ticker_of(symbol)),
                         params={"interval": interval, "range": range_}, timeout=20)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        _cache[key] = (now, res)
        return res
    except Exception as e:
        log.warning("fetch failed %s %s %s: %s", symbol, interval, range_, e)
        return None


def get_intraday_bars(symbol: str, interval: str = "5m", range_: str = "5d") -> pd.DataFrame:
    """Return DataFrame with columns time(open) OHLCV for the given intraday interval."""
    res = _fetch_chart(symbol, interval, range_)
    if not res:
        return pd.DataFrame()
    ts = res.get("timestamp") or []
    q = res.get("indicators", {}).get("quote", [{}])[0]
    df = pd.DataFrame({
        "open": q.get("open", []),
        "high": q.get("high", []),
        "low": q.get("low", []),
        "close": q.get("close", []),
        "volume": q.get("volume", []),
    }, index=pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata"))
    df = df.dropna(subset=["close"])
    df.index.name = "time"
    return df


def get_quote(symbol: str) -> dict:
    """Latest quote: price, prev close, day change %, volume, market time."""
    res = _fetch_chart(symbol, "1d", "1d")
    if not res:
        return {}
    meta = res.get("meta", {})
    return {
        "symbol": symbol,
        "price": meta.get("regularMarketPrice"),
        "prev_close": meta.get("chartPreviousClose") or meta.get("previousClose"),
        "day_change_pct": meta.get("regularMarketChangePercent"),
        "volume": meta.get("regularMarketVolume"),
        "market_time": meta.get("regularMarketTime"),
        "52wk_high": meta.get("fiftyTwoWeekHigh"),
        "52wk_low": meta.get("fiftyTwoWeekLow"),
        "exchange_delay": meta.get("exchangeDataDelayedBy"),
    }


def batch_quotes(symbols: list[str], workers: int = 8) -> dict:
    """Fetch quotes for many symbols with simple throttling."""
    import concurrent.futures as cf
    out = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get_quote, s): s for s in symbols}
        for fut in cf.as_completed(futs):
            s = futs[fut]
            try:
                out[s] = fut.result()
            except Exception:
                out[s] = {}
            time.sleep(0.25)  # be gentle on the free endpoint
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    q = get_quote("RELIANCE")
    print("RELIANCE quote:", q)
    bars = get_intraday_bars("RELIANCE", "5m", "1d")
    print("bars:", len(bars))
    print(bars.tail(3))
    bq = batch_quotes(["TCS", "INFY", "HDFCBANK"])
    for s, d in bq.items():
        print(s, d.get("price"), round(d.get("day_change_pct") or 0, 2), "%")
