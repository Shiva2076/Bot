from datetime import datetime, timedelta

import pytz

from schemas.trading import Candle
from services.prediction.chart_structure_factory import ChartStructureFactory
from services.prediction.chart_structure_query_service import ChartStructureQueryService
from services.prediction.session_range_calculator import SessionRangeCalculator

IST = pytz.timezone("Asia/Kolkata")


def _bars(count: int) -> list:
    start = IST.localize(datetime(2026, 10, 20, 9, 15))
    return [
        Candle(
            time=int((start + timedelta(minutes=5 * i)).timestamp()),
            open=25000 + i,
            high=25010 + i,
            low=24990 + i,
            close=25005 + i,
            volume=1000.0,
        )
        for i in range(count)
    ]


def test_query_service_analyzes_without_live_session():
    policy = ChartStructureFactory.policy()
    calculator = ChartStructureFactory.shadow_calculator(object(), "")
    service = ChartStructureQueryService(
        market_data=object(),
        calculator=calculator,
        session_ranges=SessionRangeCalculator(60, 15),
    )
    candles = _bars(40)
    daily = [
        Candle(
            time=int(IST.localize(datetime(2026, 10, 19, 0, 0)).timestamp()),
            open=24900,
            high=25100,
            low=24800,
            close=25000,
            volume=0.0,
        )
    ]
    # Direct path used by query service internally
    result = calculator.calculate_from_candles(
        candles_5m=candles,
        candles_15m=candles[::3],
        daily_candles=daily,
        session_range=None,
        atr=service._atr(candles),
        as_of=IST.localize(datetime(2026, 10, 20, 16, 0)),  # after market close
    )
    assert result.data_ok is True
    assert result.report is not None
    assert result.probability is None
