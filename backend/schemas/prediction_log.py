from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.options import OptionType, OptionUnderlying
from schemas.prediction import PredictionDirection


class OutcomeStatus(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


class DirectionResult(str, Enum):
    HIT = "HIT"
    MISS = "MISS"
    FLAT = "FLAT"
    NA = "NA"


class HorizonMinutes(int, Enum):
    M15 = 15
    M30 = 30
    M60 = 60


class PredictionLogCreate(BaseModel):
    underlying: OptionUnderlying
    expiry: date
    spot: float
    lot_size: int
    direction: PredictionDirection
    score: float
    confidence: float
    session_label: str
    is_expiry_day: bool
    scorer_version: str
    data_version: str
    factors: List[Dict[str, Any]]
    factor_scores: Dict[str, float]
    metrics: Dict[str, Any]
    cluster_scores: Dict[str, Any]
    regime: Dict[str, Any]
    shadow_features: Dict[str, Any]
    contract_symbol: Optional[str]
    contract_strike: Optional[float]
    contract_option_type: Optional[OptionType]
    entry_premium: Optional[float]
    predicted_at: datetime


class HorizonObservation(BaseModel):
    minutes: HorizonMinutes
    direction: PredictionDirection
    entry_spot: float
    later_spot: float
    entry_premium: Optional[float]
    later_premium: Optional[float]
    lot_size: Optional[int]


class HorizonOutcome(BaseModel):
    minutes: HorizonMinutes
    spot: float
    spot_change_pct: float
    direction_result: DirectionResult
    premium: Optional[float] = None
    premium_change_pct: Optional[float] = None
    net_pnl_per_lot: Optional[float] = None


class PredictionLogView(BaseModel):
    id: int
    underlying: OptionUnderlying
    expiry: date
    spot: float
    lot_size: Optional[int]
    direction: PredictionDirection
    score: float
    confidence: float
    session_label: str
    is_expiry_day: bool
    scorer_version: str
    data_version: str
    factors: List[Dict[str, Any]]
    factor_scores: Dict[str, float]
    metrics: Dict[str, Any]
    cluster_scores: Optional[Dict[str, Any]]
    regime: Optional[Dict[str, Any]]
    shadow_features: Optional[Dict[str, Any]]
    contract_symbol: Optional[str]
    contract_strike: Optional[float]
    contract_option_type: Optional[str]
    entry_premium: Optional[float]
    predicted_at: datetime
    outcome_status: OutcomeStatus
    spot_15m: Optional[float] = None
    spot_change_pct_15m: Optional[float] = None
    direction_result_15m: Optional[DirectionResult] = None
    premium_15m: Optional[float] = None
    premium_change_pct_15m: Optional[float] = None
    net_pnl_15m: Optional[float] = None
    spot_30m: Optional[float] = None
    spot_change_pct_30m: Optional[float] = None
    direction_result_30m: Optional[DirectionResult] = None
    premium_30m: Optional[float] = None
    premium_change_pct_30m: Optional[float] = None
    net_pnl_30m: Optional[float] = None
    spot_60m: Optional[float] = None
    spot_change_pct_60m: Optional[float] = None
    direction_result_60m: Optional[DirectionResult] = None
    premium_60m: Optional[float] = None
    premium_change_pct_60m: Optional[float] = None
    net_pnl_60m: Optional[float] = None
    outcomes_resolved_at: Optional[datetime] = None


class PredictionLogList(BaseModel):
    logs: List[PredictionLogView]
    count: int = Field(ge=0)
