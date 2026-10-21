from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class AngelCredentials(BaseModel):
    api_key: str
    client_code: str
    pin: str
    totp_secret: str


class AngelEnvelope(BaseModel):
    errorcode: Optional[str] = None


class AngelLoginRequest(BaseModel):
    clientcode: str
    password: str
    totp: str


class AngelLoginData(BaseModel):
    jwt_token: str = Field(alias="jwtToken")


class AngelLoginResponse(BaseModel):
    status: bool
    message: str
    errorcode: Optional[str] = None
    data: Optional[AngelLoginData] = None


class AngelQuoteRequest(BaseModel):
    mode: str
    exchange_tokens: Dict[str, List[str]] = Field(serialization_alias="exchangeTokens")


class AngelDepthLevel(BaseModel):
    price: float
    quantity: float


class AngelDepth(BaseModel):
    buy: List[AngelDepthLevel]
    sell: List[AngelDepthLevel]


class AngelQuote(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    exchange: str
    trading_symbol: str = Field(alias="tradingSymbol")
    symbol_token: str = Field(alias="symbolToken")
    ltp: float
    close: float
    net_change: float = Field(alias="netChange")
    percent_change: float = Field(alias="percentChange")
    open_interest: float = Field(default=0.0, alias="opnInterest")
    trade_volume: float = Field(default=0.0, alias="tradeVolume")
    exch_feed_time: Optional[str] = Field(default=None, alias="exchFeedTime")
    exch_trade_time: Optional[str] = Field(default=None, alias="exchTradeTime")
    depth: Optional[AngelDepth] = None


class AngelQuoteData(BaseModel):
    fetched: List[AngelQuote]


class AngelQuoteResponse(BaseModel):
    status: bool
    message: str
    errorcode: Optional[str] = None
    data: Optional[AngelQuoteData] = None


class AngelCandleRequest(BaseModel):
    exchange: str
    symboltoken: str
    interval: str
    fromdate: str
    todate: str


class AngelCandleResponse(BaseModel):
    status: bool
    message: str
    errorcode: Optional[str] = None
    data: Optional[List[Tuple[str, float, float, float, float, float]]] = None


class AngelScrip(BaseModel):
    token: str
    symbol: str
    name: str
    expiry: str
    strike: str
    lotsize: str
    instrumenttype: str
    exch_seg: str


class AngelInstrumentRef(BaseModel):
    exchange: str
    token: str
