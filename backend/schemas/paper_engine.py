from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.options import OptionType, OptionUnderlying
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction


class PaperSignalEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NON_ACTIONABLE = "NON_ACTIONABLE"
    REJECTED_GATE = "REJECTED_GATE"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_FILL = "REJECTED_FILL"
    REJECTED_RISK = "REJECTED_RISK"
    REJECTED_INVALID_LEVELS = "REJECTED_INVALID_LEVELS"


class PaperExecutionStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class PaperLifecycleEvent(str, Enum):
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    PAPER_ENTRY_REQUESTED = "PAPER_ENTRY_REQUESTED"
    PAPER_ENTRY_FILLED = "PAPER_ENTRY_FILLED"
    PAPER_EXIT_TRIGGERED = "PAPER_EXIT_TRIGGERED"
    PAPER_POSITION_CLOSED = "PAPER_POSITION_CLOSED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class PaperSignalEventRecord(BaseModel):
    timestamp: datetime
    event_type: PaperLifecycleEvent
    details: Optional[Dict[str, Any]] = None


class PaperSignalBase(BaseModel):
    signal_uuid: str
    session_date: date
    generated_at: datetime
    underlying: OptionUnderlying
    strategy: str = "OPTION_PREDICTION"
    direction: PredictionDirection
    score: float
    raw_score: Optional[float] = None
    signal_score: Optional[float] = None
    confidence: Optional[float] = None
    scorer_version: str

    spot_level: Optional[float] = None
    contract_symbol: Optional[str] = None
    contract_strike: Optional[float] = None
    contract_expiry: Optional[date] = None
    contract_option_type: Optional[OptionType] = None
    entry_premium: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None

    quote_ltp: Optional[float] = None
    quote_bid: Optional[float] = None
    quote_ask: Optional[float] = None
    quote_volume: Optional[float] = None
    quote_oi: Optional[float] = None
    quote_exchange_timestamp: Optional[datetime] = None
    quote_provider: Optional[str] = None
    quote_freshness: Optional[DataFreshness] = None

    gate_reason: Optional[GateReason] = None
    premarket_action: Optional[RecommendedAction] = None
    premarket_wait_trigger: Optional[str] = None
    freshness_diagnostics: Optional[List[Dict[str, Any]]] = None

    eligibility_status: PaperSignalEligibility
    execution_status: PaperExecutionStatus = PaperExecutionStatus.SKIPPED
    rejection_reasons: List[str] = Field(default_factory=list)

    trade_id: Optional[int] = None
    prediction_snapshot: Optional[Dict[str, Any]] = None
    events: List[PaperSignalEventRecord] = Field(default_factory=list)


class PaperSignalCreate(PaperSignalBase):
    pass


class PaperSignalView(PaperSignalBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class PaperEngineStatus(BaseModel):
    enabled: bool = False
    mode: str = "PAPER_TRADING_ONLY"
    active_positions: int = 0
    rejection_counters: Dict[str, int] = Field(default_factory=dict)
    last_run_at: Optional[datetime] = None
    unresolved_safety_notes: List[str] = Field(default_factory=list)
