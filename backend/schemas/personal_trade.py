from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import AwareDatetime, BaseModel, Field


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeType(str, Enum):
    PAPER = "PAPER"
    MANUAL = "MANUAL"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TradeExitRequest(BaseModel):
    exit_price: float = Field(ge=0)
    exit_time: AwareDatetime
    exit_reason: str = Field(default="MANUAL", min_length=1, max_length=50)


class PaperTradeOpened(BaseModel):
    symbol: str
    quantity: int
    entry_price: float
    invested_amount: float
    stop_loss: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    confidence: Optional[float]
    market_regime: Optional[str]


class PnlResult(BaseModel):
    pnl: float
    pnl_pct: float


class PersonalTradeView(BaseModel):
    id: int
    symbol: str
    action: TradeAction
    trade_type: TradeType
    status: TradeStatus
    quantity: int
    entry_price: float
    entry_time: datetime
    invested_amount: float
    exit_price: Optional[float]
    exit_time: Optional[datetime]
    exit_reason: Optional[str]
    current_price: Optional[float]
    stop_loss: Optional[float]
    target_1: Optional[float]
    pnl: float
    pnl_pct: float


class DailyTradeSummary(BaseModel):
    trade_date: date
    entries: int
    exits: int
    wins: int
    losses: int
    realized_pnl: float
    unrealized_pnl: float
    trades: List[PersonalTradeView]


class PortfolioPnlSummary(BaseModel):
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    today_pnl: float
    open_invested: float
    open_positions: int
    closed_trades: int
    win_rate: float


class PersonalHistoryResponse(BaseModel):
    as_of: datetime
    summary: PortfolioPnlSummary
    open_positions: List[PersonalTradeView]
    days: List[DailyTradeSummary]
