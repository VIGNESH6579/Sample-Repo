from datetime import datetime
from zoneinfo import ZoneInfo

from simple_logic import MarketSnapshot, Position, SimpleLogic

IST = ZoneInfo('Asia/Kolkata')
NOW = datetime(2026, 8, 23, 10, 0, tzinfo=IST)


def snap(symbol, side):
    base = dict(symbol=symbol, ltp=101, vwap=100, day_high=100, day_low=90, volume=200, average_volume=100,
                call_oi_change_pct=-5, put_oi_change_pct=-10, call_spread=1.0, put_spread=1.0,
                atm_call_premium=10, atm_put_premium=12, timestamp=NOW)
    if side == 'PUT':
        base.update(ltp=89, vwap=100, day_high=110, day_low=90)
    return MarketSnapshot(**base)


def main():
    logic = SimpleLogic()
    result = logic.candidates([snap('RELIANCE', 'CALL'), snap('INFY', 'PUT')], NOW)
    assert {x.side for x in result} == {'CALL', 'PUT'}
    result = logic.candidates([snap('LTIM', 'CALL'), snap('RELIANCE', 'CALL'), snap('INFY', 'CALL')], NOW)
    assert {item.symbol for item in result} == {'RELIANCE', 'INFY'}
    position = Position('RELIANCE', 'CALL', 10, 101, NOW)
    assert logic.should_exit(position, 14, 101, 100, 90, NOW)[0]
    assert logic.should_exit(position, 7.4, 101, 100, 90, NOW)[0]
    assert logic.should_exit(position, 10, 101, 100, 90, NOW.replace(hour=10, minute=46))[0]
    assert logic.should_exit(position, 10, 99, 100, 90, NOW)[0]
    print('all Simple Logic tests passed')


if __name__ == '__main__':
    main()
