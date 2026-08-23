from datetime import datetime
from zoneinfo import ZoneInfo

import engine

IST = ZoneInfo('Asia/Kolkata')
monitor = engine.Monitor()
messages = []
monitor._notify = lambda title, message, priority='default', tags='': messages.append((title, message))

start = datetime(2026, 8, 24, 9, 15, tzinfo=IST)
monitor._send_day_start(start)
monitor._send_day_start(start)
assert len(messages) == 1
assert messages[0][0] == 'Simple Logic DAY START'
assert 'Stocks loaded: 207' in messages[0][1]

eod = datetime(2026, 8, 24, 15, 40, tzinfo=IST)
monitor._send_eod(eod)
monitor._send_eod(eod)
assert len(messages) == 2
assert messages[1][0] == 'Simple Logic EOD REPORT'
assert 'Universe: 207 stocks' in messages[1][1]
print('daily report tests passed')
