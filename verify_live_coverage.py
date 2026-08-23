from tradingview_adapter import TradingViewScanner
from universe import load_universe

scanner = TradingViewScanner()
rows = []
columns = ['name', 'close', 'high', 'low', 'VWAP', 'volume', 'average_volume_10d_calc']
for start in range(0, len(load_universe()), 50):
    symbols = [row['ticker'] for row in load_universe()[start:start + 50]]
    rows.extend(scanner._scan(symbols, columns))
returned = {row.get('s', '').split(':')[-1] for row in rows}
expected = {row['ticker'] for row in load_universe()}
missing = sorted(expected - returned)
print('expected', len(expected), 'returned_rows', len(rows), 'unique_returned', len(returned), 'missing', len(missing))
print('missing_symbols', missing)
