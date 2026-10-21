from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class MarketSentiment(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class VolatilityBand(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class RecommendedAction(str, Enum):
    WATCH = "WATCH"
    WAIT = "WAIT"
    NO_TRADE = "NO_TRADE"


class IndexMove(BaseModel):
    symbol: str
    name: str
    last: float
    change_pct: float
    sentiment: MarketSentiment
    timestamp: datetime
    source: str


class GiftNiftySnapshot(BaseModel):
    available: bool
    last: Optional[float] = None
    change_pct: Optional[float] = None
    sentiment: MarketSentiment = MarketSentiment.INSUFFICIENT_DATA
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    warning: Optional[str] = None


class IndiaVixSnapshot(BaseModel):
    available: bool
    value: Optional[float] = None
    change_pct: Optional[float] = None
    band: VolatilityBand = VolatilityBand.UNKNOWN
    trend: str = "UNKNOWN"
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    warning: Optional[str] = None


class BreadthSnapshot(BaseModel):
    available: bool
    advancing: int = 0
    declining: int = 0
    unchanged: int = 0
    advance_decline_ratio: float = 0.0
    advancing_pct: float = 0.0
    session_label: str = "UNKNOWN"
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    warning: Optional[str] = None


class NiftyOpeningContext(BaseModel):
    available: bool
    previous_close: Optional[float] = None
    last: Optional[float] = None
    previous_high: Optional[float] = None
    previous_low: Optional[float] = None
    gap_pct: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    session_phase: str = "UNKNOWN"
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    warning: Optional[str] = None


class SectorSnapshot(BaseModel):
    name: str
    change_pct: float
    status: str


class PremarketFactor(BaseModel):
    name: str
    sentiment: MarketSentiment
    score: float
    weight: float
    included: bool
    detail: str


class PremarketReport(BaseModel):
    report_date: date
    generated_at: datetime
    session_phase: str
    is_trading_day: bool
    overall_sentiment: MarketSentiment
    heuristic_confidence: float = Field(description="Heuristic 0-100 score, not a probability of success")
    directional_score: float
    recommended_action: RecommendedAction
    global_markets: List[IndexMove]
    gift_nifty: GiftNiftySnapshot
    india_vix: IndiaVixSnapshot
    breadth: BreadthSnapshot
    nifty_context: NiftyOpeningContext
    strongest_sectors: List[SectorSnapshot]
    weakest_sectors: List[SectorSnapshot]
    factors: List[PremarketFactor]
    excluded_indicators: List[str]
    bullish_scenarios: List[str]
    bearish_scenarios: List[str]
    key_risks: List[str]
    upcoming_events: List[str]
    reasons: List[str]
    data_quality_warnings: List[str]
    score_note: str = (
        "Heuristic weighted score from available pre-market inputs. "
        "Not calibrated as a probability and not a guarantee of direction."
    )


class PremarketHistoryResponse(BaseModel):
    reports: List[PremarketReport]
