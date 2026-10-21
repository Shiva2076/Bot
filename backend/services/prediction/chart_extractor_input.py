from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from schemas.prediction import SessionRange
from schemas.trading import Candle
from services.prediction.chart_prior_day_levels import PriorDayLevels


class ChartExtractorInput(BaseModel):
    candles_5m: List[Candle]
    candles_15m: List[Candle]
    prior_day: Optional[PriorDayLevels]
    today_open: Optional[float]
    session_range: Optional[SessionRange]
    atr: float
    as_of: datetime
