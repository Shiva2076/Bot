from datetime import datetime
from typing import List, Optional

from schemas.prediction import SessionRange
from schemas.trading import Candle
from services.prediction.chart_candle_policy import ChartCandlePolicy
from services.prediction.chart_extractor_input import ChartExtractorInput
from services.prediction.chart_prior_day_levels import ChartPriorDayLevelBuilder


class ChartStructureMapper:
    def __init__(self, policy: ChartCandlePolicy, prior_day_builder: ChartPriorDayLevelBuilder):
        self._policy = policy
        self._prior_day_builder = prior_day_builder

    def map(
        self,
        candles_5m: List[Candle],
        candles_15m: List[Candle],
        daily_candles: List[Candle],
        session_range: Optional[SessionRange],
        atr: float,
        as_of: datetime,
    ) -> ChartExtractorInput:
        completed_5m = self._policy.completed(candles_5m, 5, as_of)
        completed_15m = self._policy.completed(candles_15m, 15, as_of)
        prior_day = self._prior_day_builder.build(daily_candles, as_of)
        today_open = self._prior_day_builder.today_open(candles_5m, as_of)
        return ChartExtractorInput(
            candles_5m=completed_5m,
            candles_15m=completed_15m,
            prior_day=prior_day,
            today_open=today_open,
            session_range=session_range,
            atr=atr,
            as_of=as_of,
        )
