from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.options import OptionUnderlying
from schemas.order_entry import OverrideReason
from schemas.personal_trade import PersonalTradeView, TradeAction


class InstrumentKind(str, Enum):
    INDEX = "INDEX"
    STOCK = "STOCK"
    OPTION = "OPTION"


class CandleInterval(str, Enum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_DAY = "1d"


class ExitReason(str, Enum):
    MANUAL = "MANUAL"
    SL_HIT = "SL_HIT"
    TARGET_HIT = "TARGET_HIT"
    EXPIRED = "EXPIRED"
    SQUARE_OFF = "SQUARE_OFF"


class Instrument(BaseModel):
    symbol: str
    name: str
    kind: InstrumentKind
    lot_size: int
    option_underlying: Optional[OptionUnderlying] = None


class Tick(BaseModel):
    symbol: str
    ltp: float
    prev_close: float
    change: float
    change_pct: float
    timestamp: datetime
    provider: str
    fetched_at: Optional[datetime] = None
    exchange_timestamp: Optional[datetime] = None


class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleSeries(BaseModel):
    symbol: str
    interval: CandleInterval
    provider: str
    candles: List[Candle]


class MarketOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=40)
    action: TradeAction
    lots: int = Field(gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    target: Optional[float] = Field(default=None, gt=0)
    override_reason: Optional[OverrideReason] = None


class PortfolioOpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: TradeAction
    entry: float = Field(gt=0, description="Signal entry estimate used only for position sizing")
    stop_loss: float = Field(gt=0)
    target: Optional[float] = Field(default=None, gt=0)
    override_reason: Optional[OverrideReason] = None


class OpenPositionsResponse(BaseModel):
    positions: List[PersonalTradeView]
