from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class OptionUnderlying(str, Enum):
    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class ParsedOptionSymbol(BaseModel):
    underlying: OptionUnderlying
    expiry: date
    strike: float
    option_type: OptionType


class OptionContract(BaseModel):
    symbol: str
    token: str
    underlying: OptionUnderlying
    expiry: date
    strike: float
    option_type: OptionType
    lot_size: int
    display_name: str


class OptionQuote(BaseModel):
    symbol: str
    display_name: str
    ltp: float
    change: float
    change_pct: float
    open_interest: float
    volume: float
    bid: Optional[float]
    ask: Optional[float]
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    fetched_at: Optional[datetime] = None
    exchange_timestamp: Optional[datetime] = None


class OptionGreeks(BaseModel):
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float


class OptionPricingInput(BaseModel):
    option_type: OptionType
    spot: float
    strike: float
    years_to_expiry: float
    rate: float


class FuturesContract(BaseModel):
    symbol: str
    token: str
    underlying: OptionUnderlying
    expiry: date
    lot_size: int


class FuturesQuote(BaseModel):
    symbol: str
    ltp: float
    open_interest: float
    volume: float
    bid: Optional[float]
    ask: Optional[float]


class OptionChainRow(BaseModel):
    strike: float
    call: Optional[OptionQuote]
    put: Optional[OptionQuote]


class OptionChain(BaseModel):
    underlying: OptionUnderlying
    expiry: date
    spot: float
    atm_strike: float
    lot_size: int
    rows: List[OptionChainRow]


class OptionExpiries(BaseModel):
    underlying: OptionUnderlying
    expiries: List[date]
