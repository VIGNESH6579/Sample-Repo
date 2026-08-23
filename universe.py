from __future__ import annotations

import json
from pathlib import Path


DATA = Path(__file__).parent / 'data' / 'universe.json'


def load_universe() -> list[dict]:
    payload = json.loads(DATA.read_text())
    stocks = payload.get('stocks', [])
    if payload.get('unresolved'):
        raise RuntimeError(f"Unresolved stock mappings: {payload['unresolved']}")
    return [row for row in stocks if row.get('ticker') and 'LTIM' not in row.get('name', '').upper()]


def tickers() -> list[str]:
    return [row['ticker'] for row in load_universe()]
