from datetime import date, datetime
from typing import List

from pydantic import BaseModel

from schemas.options import OptionChainRow, OptionUnderlying
from schemas.prediction import ChainShadowFeatures, FuturesFlowState


class OptionChainSnapshotCreate(BaseModel):
    underlying: OptionUnderlying
    expiry: date
    captured_at: datetime
    spot: float
    atm_strike: float
    lot_size: int
    rows: List[OptionChainRow]
    shadow: ChainShadowFeatures
    data_version: str


class FuturesSnapshotCreate(BaseModel):
    state: FuturesFlowState
    data_version: str
