from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.personal_trade import TradeAction


class OrbDecision(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"
    INVALIDATED = "INVALIDATED"


class OpeningRange(BaseModel):
    high: float
    low: float
    start: datetime
    end: datetime
    bar_count: int


class OrbSignal(BaseModel):
    symbol: str
    session_date: date
    decision: OrbDecision
    action: Optional[TradeAction] = None
    range: Optional[OpeningRange] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    quantity: Optional[int] = None
    signal_time: Optional[datetime] = None
    vwap_at_signal: Optional[float] = None
    volume_at_signal: Optional[float] = None
    volume_ma_at_signal: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    rejection_reason: Optional[str] = None
    inputs: dict = Field(default_factory=dict)


class OrbEvaluateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)


class OrbExecuteResponse(BaseModel):
    signal: OrbSignal
    trade_id: Optional[int] = None
    executed: bool
    gate_reasons: List[str] = Field(default_factory=list)
