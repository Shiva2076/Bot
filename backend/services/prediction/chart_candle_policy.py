from datetime import date, datetime, timedelta
from typing import List

import pytz

from schemas.trading import Candle

IST = pytz.timezone("Asia/Kolkata")


class ChartCandlePolicy:
    """Keeps only completed candles relative to as_of (no forming bar)."""

    def completed(self, candles: List[Candle], interval_minutes: int, as_of: datetime) -> List[Candle]:
        local_as_of = as_of.astimezone(IST)
        horizon = timedelta(minutes=interval_minutes)
        completed: List[Candle] = []
        for candle in candles:
            start = datetime.fromtimestamp(candle.time, IST)
            if start + horizon <= local_as_of:
                completed.append(candle)
        return completed

    def session_date(self, candle: Candle) -> date:
        return datetime.fromtimestamp(candle.time, IST).date()
