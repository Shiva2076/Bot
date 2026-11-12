from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.options import OptionUnderlying
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction


class TradeDecisionStatus(str, Enum):
    TRADE = "TRADE"
    NO_TRADE = "NO_TRADE"


class TradeDecisionBlockCode(str, Enum):
    PREMARKET_NO_TRADE = "PREMARKET_NO_TRADE"
    SESSION_CLOSED = "SESSION_CLOSED"
    FRESHNESS_UNVERIFIED = "FRESHNESS_UNVERIFIED"
    WAITING_SETUP = "WAITING_SETUP"
    NO_CONTRACT = "NO_CONTRACT"
    RISK_LIMIT = "RISK_LIMIT"
    SETUP_NOT_ACTIONABLE = "SETUP_NOT_ACTIONABLE"


class TradeDecisionGateDiagnostic(BaseModel):
    code: TradeDecisionBlockCode
    passed: bool
    detail: str


class TradeDecisionInputs(BaseModel):
    """Authoritative gate inputs already resolved by services; no scoring here."""

    underlying: OptionUnderlying
    expiry: date
    session_phase: str
    session_permitted: bool
    premarket_action: Optional[RecommendedAction]
    premarket_available: bool
    prediction_direction: Optional[PredictionDirection]
    gate_reason: Optional[GateReason]
    data_freshness: Optional[DataFreshness]
    contract_symbol: Optional[str]
    exchange_freshness_verified: bool
    risk_allowed: bool
    risk_reasons: List[str] = Field(default_factory=list)
    open_manual_override: bool = False


class TradeDecisionResponse(BaseModel):
    status: TradeDecisionStatus
    reason: str
    block_code: Optional[TradeDecisionBlockCode] = None
    underlying: OptionUnderlying
    expiry: date
    session_phase: str
    premarket_action: Optional[RecommendedAction]
    prediction_direction: Optional[PredictionDirection]
    gate_reason: Optional[GateReason]
    data_freshness: Optional[DataFreshness]
    contract_symbol: Optional[str]
    manual_override_eligible: bool = False
    override_note: Optional[str] = None
    diagnostics: List[TradeDecisionGateDiagnostic] = Field(default_factory=list)
    disclaimer: str = (
        "TRADE means an actionable setup and mandatory entry safety checks passed; "
        "it does not authorize an order and does not imply profitability. "
        "The order endpoint revalidates all conditions on submit."
    )
