from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, StringConstraints

from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction

OVERRIDE_REASON_MAX_LENGTH = 500

OverrideReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=OVERRIDE_REASON_MAX_LENGTH),
]


class OrderSource(str, Enum):
    SYSTEM_SIGNAL = "SYSTEM_SIGNAL"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    LEGACY = "LEGACY"


class EntryOrigin(str, Enum):
    """Server-side origin of an entry request. Never accepted from the client."""

    API = "API"
    ORB_STRATEGY = "ORB_STRATEGY"
    AUTO_PAPER = "AUTO_PAPER"


class PredictionGateSnapshot(BaseModel):
    available: bool
    direction: Optional[PredictionDirection] = None
    gate_reason: Optional[GateReason] = None
    data_freshness: Optional[DataFreshness] = None
    session_status: Optional[str] = None
    contract_symbol: Optional[str] = None
    generated_at: Optional[datetime] = None
    log_id: Optional[int] = None
    note: Optional[str] = None


class SignalMatch(BaseModel):
    matched: bool
    snapshot: PredictionGateSnapshot


class OrderClassificationInput(BaseModel):
    premarket_action: RecommendedAction
    origin: EntryOrigin
    override_reason: Optional[str]
    matches_actionable_signal: bool


class EntryAudit(BaseModel):
    order_source: OrderSource
    override_reason: Optional[str]
    premarket_action: RecommendedAction
    prediction_gate: PredictionGateSnapshot
