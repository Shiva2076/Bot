from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from schemas.options import OptionUnderlying
from schemas.prediction import PredictionDirection
from schemas.prediction_log import DirectionResult


class PredictionResearchOutcomeCreate(BaseModel):
    prediction_log_id: int
    underlying: OptionUnderlying
    predicted_at: datetime
    gate_reason: Optional[str]
    premarket_wait_trigger: Optional[str]
    score: float
    implied_direction: PredictionDirection
    spot_result_15m: Optional[DirectionResult]
    spot_result_30m: Optional[DirectionResult]
    spot_result_60m: Optional[DirectionResult]
    spot_change_pct_15m: Optional[float]
    spot_change_pct_30m: Optional[float]
    spot_change_pct_60m: Optional[float]
    hypothetical_net_pnl_15m: Optional[float]
    hypothetical_net_pnl_30m: Optional[float]
    hypothetical_net_pnl_60m: Optional[float]
    hypothetical: bool = Field(default=True)
