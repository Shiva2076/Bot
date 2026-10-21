from datetime import datetime, timezone
from typing import List

import pytz

from schemas.prediction import ChartStructureFeatures, SessionRange
from schemas.trading import Candle, CandleInterval
from services.prediction.chart_structure_shadow_calculator import ChartStructureShadowCalculator
from services.prediction.intraday_indicator_provider import INTERVAL_MINUTES
from services.prediction.session_range_calculator import SessionRangeCalculator
from services.trading.failover_market_data import FailoverMarketData

IST = pytz.timezone("Asia/Kolkata")
ATR_PERIOD = 14


class ChartStructureQueryService:
    """Off-session-safe chart structure fetch; shadow-only, no prediction gates."""

    def __init__(
        self,
        market_data: FailoverMarketData,
        calculator: ChartStructureShadowCalculator,
        session_ranges: SessionRangeCalculator,
    ):
        self._market_data = market_data
        self._calculator = calculator
        self._session_ranges = session_ranges

    async def analyze(self, symbol: str) -> ChartStructureFeatures:
        now = datetime.now(timezone.utc)
        series_5m = await self._market_data.get_candles(symbol, CandleInterval.FIVE_MINUTES)
        series_15m = await self._market_data.get_candles(symbol, CandleInterval.FIFTEEN_MINUTES)
        series_daily = await self._market_data.get_candles(symbol, CandleInterval.ONE_DAY)
        atr = self._atr(series_5m.candles)
        session_range = self._session_ranges.compute(
            series_5m.candles,
            INTERVAL_MINUTES[CandleInterval.FIVE_MINUTES],
            now,
        )
        return self._calculator.calculate_from_candles(
            candles_5m=series_5m.candles,
            candles_15m=series_15m.candles,
            daily_candles=series_daily.candles,
            session_range=session_range,
            atr=atr,
            as_of=now,
        )

    @staticmethod
    def _atr(candles: List[Candle]) -> float:
        if len(candles) < 2:
            return 0.0
        ranges: List[float] = []
        prev_close = candles[0].close
        for candle in candles[1:]:
            tr = max(
                candle.high - candle.low,
                abs(candle.high - prev_close),
                abs(candle.low - prev_close),
            )
            ranges.append(tr)
            prev_close = candle.close
        window = ranges[-ATR_PERIOD:] if len(ranges) >= ATR_PERIOD else ranges
        if not window:
            return 0.0
        return round(sum(window) / len(window), 4)
