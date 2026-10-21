from datetime import datetime, timedelta
from typing import List

import pytz

from schemas.prediction import SessionRangeKind
from schemas.trading import Candle
from services.prediction.session_range_calculator import SessionRangeCalculator

IST = pytz.timezone("Asia/Kolkata")


def _bars(day: int, count: int, high: float, low: float) -> List[Candle]:
    start = IST.localize(datetime(2026, 10, day, 9, 15))
    return [
        Candle(
            time=int((start + timedelta(minutes=5 * i)).timestamp()),
            open=low + 1, high=high + i, low=low - i, close=low + 2, volume=0.0,
        )
        for i in range(count)
    ]


def _calc() -> SessionRangeCalculator:
    return SessionRangeCalculator(initial_balance_minutes=60, opening_range_minutes=15)


def test_uses_today_only_not_oldest_day():
    candles = _bars(19, 75, high=500.0, low=100.0) + _bars(20, 14, high=200.0, low=150.0)
    result = _calc().compute(candles, 5, IST.localize(datetime(2026, 10, 20, 10, 30)))
    assert result is not None
    assert result.kind == SessionRangeKind.INITIAL_BALANCE
    assert result.high == 211.0
    assert result.low == 139.0


def test_opening_range_before_initial_balance_forms():
    candles = _bars(20, 6, high=200.0, low=150.0)
    result = _calc().compute(candles, 5, IST.localize(datetime(2026, 10, 20, 9, 45)))
    assert result is not None
    assert result.kind == SessionRangeKind.OPENING_RANGE
    assert result.high == 202.0
    assert result.low == 148.0


def test_none_before_opening_range_forms():
    candles = _bars(20, 2, high=200.0, low=150.0)
    assert _calc().compute(candles, 5, IST.localize(datetime(2026, 10, 20, 9, 25))) is None


def test_none_when_today_has_no_bars():
    candles = _bars(19, 75, high=500.0, low=100.0)
    assert _calc().compute(candles, 5, IST.localize(datetime(2026, 10, 20, 11, 0))) is None
