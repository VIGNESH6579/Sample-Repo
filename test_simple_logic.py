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


def test_call_and_put_candidates():
    logic = SimpleLogic()
    result = logic.candidates([snap('RELIANCE', 'CALL'), snap('INFY', 'PUT')], NOW)
    assert {x.side for x in result} == {'CALL', 'PUT'}


def test_ltim_is_excluded_and_top_one_selected():
    logic = SimpleLogic()
    result = logic.entry([snap('LTIM', 'CALL'), snap('RELIANCE', 'CALL'), snap('INFY', 'CALL')], NOW)
    assert result.symbol != 'LTIM'
    assert result.symbol == 'INFY'  # larger absolute OI score


def test_current_session_extreme_inclusive_entries():
    logic = SimpleLogic()
    call = snap('RELIANCE', 'CALL')
    call.day_high = call.ltp
    put = snap('INFY', 'PUT')
    put.day_low = put.ltp
    result = logic.candidates([call, put], NOW)
    assert {(item.symbol, item.side) for item in result} == {('RELIANCE', 'CALL'), ('INFY', 'PUT')}


def test_exit_rules():
    logic = SimpleLogic()
    position = Position('RELIANCE', 'CALL', 10, 101, NOW)
    assert logic.should_exit(position, 14, 101, 100, 90, NOW)[0]
    assert logic.should_exit(position, 7.4, 101, 100, 90, NOW)[0]
    assert logic.should_exit(position, 10, 101, 100, 90, NOW.replace(hour=10, minute=46))[0]
    assert logic.should_exit(position, 10, 99, 100, 90, NOW)[0]
