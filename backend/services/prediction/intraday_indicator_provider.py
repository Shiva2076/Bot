from datetime import datetime
from typing import Dict

import pandas as pd
import pytz

from engines.technical_analysis import run_full_analysis
from schemas.prediction import IntradayIndicators
from schemas.trading import CandleInterval
from services.prediction.session_range_calculator import SessionRangeCalculator
from services.trading.errors import MarketDataUnavailableError
from services.trading.failover_market_data import FailoverMarketData

MIN_CANDLES = 30
INTERVAL_MINUTES: Dict[CandleInterval, int] = {
    CandleInterval.ONE_MINUTE: 1,
    CandleInterval.FIVE_MINUTES: 5,
    CandleInterval.FIFTEEN_MINUTES: 15,
}


class IntradayIndicatorProvider:
    def __init__(
        self,
        market_data: FailoverMarketData,
        interval: CandleInterval,
        session_ranges: SessionRangeCalculator,
    ):
        self._market_data = market_data
        self._interval = interval
        self._session_ranges = session_ranges

    async def get(self, symbol: str) -> IntradayIndicators:
        series = await self._market_data.get_candles(symbol, self._interval)
        if len(series.candles) < MIN_CANDLES:
            raise MarketDataUnavailableError(f"Not enough {self._interval.value} candles for {symbol}")
        frame = pd.DataFrame([candle.model_dump() for candle in series.candles])
        indicators = IntradayIndicators.model_validate(run_full_analysis(frame))
        has_volume = any(c.volume > 0 for c in series.candles)
        session_range = self._session_ranges.compute(
            series.candles, INTERVAL_MINUTES[self._interval], datetime.now(pytz.utc)
        )
        return indicators.model_copy(update={
            "vwap": indicators.vwap if has_volume else None,
            "rvol": indicators.rvol if has_volume else None,
            "volume_ratio": indicators.volume_ratio if has_volume else None,
            "session_range": session_range,
        })
