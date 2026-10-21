from datetime import date, datetime
from typing import List, Optional

import pytz
from pydantic import BaseModel

from schemas.trading import Candle
from services.prediction.chart_candle_policy import ChartCandlePolicy

IST = pytz.timezone("Asia/Kolkata")


class PriorDayLevels(BaseModel):
    session_date: date
    pdh: float
    pdl: float
    pdc: float


class ChartPriorDayLevelBuilder:
    """PDH/PDL/PDC from the latest completed prior-session daily candle."""

    def __init__(self, policy: ChartCandlePolicy):
        self._policy = policy

    def build(self, daily_candles: List[Candle], as_of: datetime) -> Optional[PriorDayLevels]:
        today = as_of.astimezone(IST).date()
        prior = [
            candle
            for candle in daily_candles
            if self._policy.session_date(candle) < today
        ]
        if not prior:
            return None
        candle = max(prior, key=lambda item: item.time)
        return PriorDayLevels(
            session_date=self._policy.session_date(candle),
            pdh=round(candle.high, 2),
            pdl=round(candle.low, 2),
            pdc=round(candle.close, 2),
        )

    def today_open(self, intraday_candles: List[Candle], as_of: datetime) -> Optional[float]:
        today = as_of.astimezone(IST).date()
        todays = [c for c in intraday_candles if self._policy.session_date(c) == today]
        if not todays:
            return None
        first = min(todays, key=lambda item: item.time)
        return round(first.open, 2)
