from pydantic import BaseModel, Field

from schemas.personal_trade import TradeAction


class CostConfig(BaseModel):
    brokerage_pct: float = Field(ge=0)
    brokerage_flat: float = Field(ge=0)
    exchange_txn_pct: float = Field(ge=0)
    sebi_pct: float = Field(ge=0)
    stamp_duty_buy_pct: float = Field(ge=0)
    stt_sell_pct: float = Field(ge=0)
    gst_pct: float = Field(ge=0)
    slippage_bps: float = Field(ge=0)


class LegCostBreakdown(BaseModel):
    notional: float
    slipped_price: float
    brokerage: float
    exchange: float
    sebi: float
    stamp: float
    stt: float
    gst: float
    total_fees: float


class RoundTripCostEstimate(BaseModel):
    entry: LegCostBreakdown
    exit: LegCostBreakdown
    total_fees: float
    total_slippage_notional: float
