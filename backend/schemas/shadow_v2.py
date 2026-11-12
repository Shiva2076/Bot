"""Inputs and configuration for the Phase 2 shadow scorer (v2.0)."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.trading import Candle


class ShadowV2Config(BaseModel):
    version: str
    pcr_change_window_minutes: float
    pcr_change_tolerance_minutes: float
    pcr_change_full_scale: float
    premarket_half_life_minutes: float
    oi_buildup_weight: float
    oi_buildup_window_minutes: float
    oi_buildup_tolerance_minutes: float
    oi_buildup_min_oi_change_pct: float
    oi_buildup_min_price_change_pct: float
    oi_buildup_full_scale_pct: float
    futures_min_session_bars: int
    futures_atr_period: int
    futures_rvol_lookback_sessions: int
    futures_rvol_min_prior_sessions: int
    iv_rank_lookback_sessions: int
    iv_rank_min_sessions: int
    iv_rank_block_buying_at: float


class ChainSnapshotPoint(BaseModel):
    """One stored option_chain_snapshots row, reduced to what v2 needs."""

    captured_at: datetime
    expiry: date
    spot: float
    strike_window: float
    near_call_oi: float
    near_put_oi: float
    near_spot_pcr: Optional[float] = None
    atm_iv: Optional[float] = None


class DailyAtmIv(BaseModel):
    session_date: date
    atm_iv: float
    expiry: date
    captured_at: datetime


class ShadowV2Inputs(BaseModel):
    chain_history: List[ChainSnapshotPoint] = Field(default_factory=list)
    daily_atm_iv: List[DailyAtmIv] = Field(default_factory=list)
    futures_symbol: Optional[str] = None
    futures_candles: Optional[List[Candle]] = None
    notes: List[str] = Field(default_factory=list)
