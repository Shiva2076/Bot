from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.personal_trade import TradeAction
from schemas.premarket import RecommendedAction


class PreTradeOrderContext(BaseModel):
    symbol: str
    action: TradeAction
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    tick_timestamp: datetime
    tick_provider: str
    open_positions: int
    starting_capital: float = Field(gt=0)
    available_cash: float
    realized_pnl_today: float
    kill_switch_active: bool
    premarket_action: Optional[RecommendedAction] = None
    data_warnings: List[str] = Field(default_factory=list)


class RiskGateDecision(BaseModel):
    allowed: bool
    reasons: List[str] = Field(default_factory=list)
