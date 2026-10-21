from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from schemas.options import OptionQuote, OptionType, OptionUnderlying


class PredictionDirection(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"
    MARKET_CLOSED = "MARKET_CLOSED"
    STALE_DATA = "STALE_DATA"
    UNKNOWN_FRESHNESS = "UNKNOWN_FRESHNESS"


class GateReason(str, Enum):
    NONE = "NONE"
    MARKET_CLOSED = "MARKET_CLOSED"
    STALE_DATA = "STALE_DATA"
    UNKNOWN_FRESHNESS = "UNKNOWN_FRESHNESS"
    MTF_CONFLICT = "MTF_CONFLICT"
    CLUSTER_DISAGREEMENT = "CLUSTER_DISAGREEMENT"
    LOW_COVERAGE = "LOW_COVERAGE"
    PREMARKET_WAIT = "PREMARKET_WAIT"
    INVALID_DATA = "INVALID_DATA"
    LOW_SIGNAL_SCORE = "LOW_SIGNAL_SCORE"
    EXPIRY_PRE_CLOSE = "EXPIRY_PRE_CLOSE"


class FreshnessBasis(str, Enum):
    EXCHANGE = "EXCHANGE"
    FETCH = "FETCH"
    UNKNOWN = "UNKNOWN"


class DataFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    MARKET_CLOSED = "MARKET_CLOSED"


class FactorBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class FactorCluster(str, Enum):
    TREND = "TREND"
    LEVELS = "LEVELS"
    OPTIONS = "OPTIONS"
    FUTURES_FLOW = "FUTURES_FLOW"
    CONTEXT = "CONTEXT"
    AGENTS = "AGENTS"
    REGIME = "REGIME"


class FactorStatus(str, Enum):
    ACTIVE = "ACTIVE"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"


class PredictionFactor(BaseModel):
    name: str
    bias: FactorBias
    score: float
    weight: float
    detail: str
    cluster: FactorCluster
    status: FactorStatus
    contribution: float = 0.0
    contribution_pct: float = 0.0
    effective_weight: float = 0.0


class AgentConsensus(BaseModel):
    action: Literal["BUY", "SELL", "NEUTRAL"]
    confidence: float
    bullish_agents: int
    bearish_agents: int
    reasons: List[str]


class SessionRangeKind(str, Enum):
    INITIAL_BALANCE = "INITIAL_BALANCE"
    OPENING_RANGE = "OPENING_RANGE"


class SessionRange(BaseModel):
    kind: SessionRangeKind
    minutes: int
    high: float
    low: float


class IntradayIndicators(BaseModel):
    price: float
    rsi: float
    macd_histogram: float
    ema_20: float
    atr: float
    supertrend_direction: int
    vwap: Optional[float] = None
    volume_ratio: Optional[float] = None
    rvol: Optional[float] = None
    session_range: Optional[SessionRange] = None
    adx: Optional[float] = None
    plus_di: Optional[float] = None
    minus_di: Optional[float] = None


class ChainMetrics(BaseModel):
    put_call_ratio: float
    max_pain: float
    call_wall: float
    put_wall: float
    total_call_oi: float
    total_put_oi: float
    call_oi_change: float = 0.0
    put_oi_change: float = 0.0
    oi_interpretation: str = "UNKNOWN"
    atm_iv: Optional[float] = None
    iv_rank: Optional[float] = None
    near_spot_pcr: Optional[float] = None
    strike_window: Optional[float] = None


class ClusterScore(BaseModel):
    score: Optional[float]
    active_factors: int
    total_factors: int
    contribution: float = 0.0
    contribution_pct: float = 0.0


class RegimeLabel(str, Enum):
    TRENDING = "TRENDING"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


class RegimeSnapshot(BaseModel):
    label: RegimeLabel
    adx: Optional[float]
    vix: Optional[float]
    vix_change_pct: Optional[float]
    atm_iv: Optional[float]
    adx_multiplier: float = 1.0


class ChainShadowFeatures(BaseModel):
    strike_window: float
    near_call_oi: float
    near_put_oi: float
    near_spot_pcr: Optional[float]
    atm_iv: Optional[float]
    iv_skew_25d: Optional[float]
    gex_per_1pct: Optional[float]
    quotes_with_iv: int
    quotes_total: int


class FuturesFlowState(BaseModel):
    underlying: OptionUnderlying
    contract_symbol: str
    expiry: date
    captured_at: datetime
    ltp: float
    spot: float
    basis: float
    basis_pct: float
    open_interest: float
    volume: float
    price_change: Optional[float]
    oi_change: Optional[float]
    volume_change: Optional[float]
    cvd_proxy: float


class StructureBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class ChartSetup(str, Enum):
    NONE = "NONE"
    SUPPORT_BREAKDOWN_RETEST = "SUPPORT_BREAKDOWN_RETEST"
    RESISTANCE_BREAKOUT_RETEST = "RESISTANCE_BREAKOUT_RETEST"
    LIQUIDITY_SWEEP_REVERSAL = "LIQUIDITY_SWEEP_REVERSAL"
    RANGE_COMPRESSION = "RANGE_COMPRESSION"
    FVG_RETEST = "FVG_RETEST"
    BREAK_OF_STRUCTURE = "BREAK_OF_STRUCTURE"
    CHANGE_OF_CHARACTER = "CHANGE_OF_CHARACTER"
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    CHANNEL = "CHANNEL"


class ChartLevelKind(str, Enum):
    PDH = "PDH"
    PDL = "PDL"
    PDC = "PDC"
    OPENING_GAP = "OPENING_GAP"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    FVG_TOP = "FVG_TOP"
    FVG_BOTTOM = "FVG_BOTTOM"
    BOS = "BOS"
    CHOCH = "CHOCH"
    NECKLINE = "NECKLINE"
    TRENDLINE = "TRENDLINE"
    CHANNEL = "CHANNEL"
    INVALIDATION = "INVALIDATION"


class ChartPatternStatus(str, Enum):
    NONE = "NONE"
    POTENTIAL = "POTENTIAL"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class ChartAnnotationCategory(str, Enum):
    LEVELS = "LEVELS"
    ZONES = "ZONES"
    FVG = "FVG"
    TRENDLINES = "TRENDLINES"
    PATTERNS = "PATTERNS"
    SCENARIOS = "SCENARIOS"


class ChartProjectionKind(str, Enum):
    CHANNEL_UPPER = "CHANNEL_UPPER"
    CHANNEL_LOWER = "CHANNEL_LOWER"
    MEASURED_MOVE = "MEASURED_MOVE"
    BREAKOUT_PATH = "BREAKOUT_PATH"
    TARGET_ZONE = "TARGET_ZONE"
    PATTERN_LABEL = "PATTERN_LABEL"


class ChartLevel(BaseModel):
    kind: ChartLevelKind
    price: float
    source: str


class ChartAnnotation(BaseModel):
    category: ChartAnnotationCategory
    kind: str
    price: Optional[float] = None
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    time_start: Optional[int] = None
    time_end: Optional[int] = None
    source: str
    status: ChartPatternStatus = ChartPatternStatus.CONFIRMED
    label: str


class ChartProjection(BaseModel):
    """Rule-based forward scenario geometry. Not a calibrated forecast."""

    kind: ChartProjectionKind
    time_start: int
    time_end: int
    price_start: float
    price_end: float
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    label: str
    side: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    status: ChartPatternStatus
    evidence: str


class ChartPatternHit(BaseModel):
    pattern: str
    status: ChartPatternStatus
    bias: StructureBias
    level: Optional[float] = None
    invalidation: Optional[float] = None
    confirmation: Optional[str] = None
    evidence: str
    time: Optional[int] = None


class ChartScenario(BaseModel):
    side: Literal["BULLISH", "BEARISH", "WAIT"]
    summary: str
    confirmation: Optional[str] = None
    invalidation: Optional[str] = None
    invalidation_price: Optional[float] = None


class ChartDataQuality(BaseModel):
    ok: bool
    ordered: bool
    duplicate_bars: int
    gap_count: int
    detail: str


class ChartAnalysisReport(BaseModel):
    structure: StructureBias
    pattern_status: ChartPatternStatus
    primary_pattern: Optional[str] = None
    evidence: List[str]
    bullish: ChartScenario
    bearish: ChartScenario
    wait: ChartScenario
    key_supports: List[float]
    key_resistances: List[float]
    data_quality: ChartDataQuality
    as_of: datetime
    narrative: Optional[str] = None
    probability: Optional[float] = None
    detail: str


class ChartStructureFeatures(BaseModel):
    as_of: datetime
    interval_5m_bars: int
    interval_15m_bars: int
    structure_5m: StructureBias
    structure_15m: StructureBias
    setup: ChartSetup
    bias: StructureBias
    action_hint: Literal["CALL", "PUT", "WAIT"]
    key_levels: List[ChartLevel]
    evidence: List[str]
    trigger: Optional[str]
    invalidation_price: Optional[float]
    invalidation_rule: Optional[str]
    probability: Optional[float] = None
    opening_gap_points: Optional[float] = None
    data_ok: bool
    detail: str
    annotations: List[ChartAnnotation] = Field(default_factory=list)
    patterns: List[ChartPatternHit] = Field(default_factory=list)
    projections: List[ChartProjection] = Field(default_factory=list)
    report: Optional[ChartAnalysisReport] = None
    data_quality: Optional[ChartDataQuality] = None

    @classmethod
    def unavailable(cls, detail: str, as_of: datetime) -> "ChartStructureFeatures":
        quality = ChartDataQuality(ok=False, ordered=False, duplicate_bars=0, gap_count=0, detail=detail)
        return cls(
            as_of=as_of,
            interval_5m_bars=0,
            interval_15m_bars=0,
            structure_5m=StructureBias.UNKNOWN,
            structure_15m=StructureBias.UNKNOWN,
            setup=ChartSetup.NONE,
            bias=StructureBias.UNKNOWN,
            action_hint="WAIT",
            key_levels=[],
            evidence=[],
            trigger=None,
            invalidation_price=None,
            invalidation_rule=None,
            probability=None,
            opening_gap_points=None,
            data_ok=False,
            detail=detail,
            annotations=[],
            patterns=[],
            projections=[],
            report=None,
            data_quality=quality,
        )


class ShadowFeatures(BaseModel):
    chain: ChainShadowFeatures
    futures: Optional[FuturesFlowState]
    chart: Optional[ChartStructureFeatures] = None


class QuoteFreshness(BaseModel):
    symbol: str
    exchange_timestamp: Optional[datetime]
    fetched_at: Optional[datetime]
    quoted_at: Optional[datetime]
    age_seconds: Optional[float]
    provider: Optional[str]
    freshness: DataFreshness
    basis: FreshnessBasis
    verified: bool


class PremiumLevels(BaseModel):
    entry: float
    stop_loss: float
    target: float


class SuggestedContract(BaseModel):
    strike: float
    option_type: OptionType
    quote: OptionQuote
    levels: PremiumLevels


class OptionPrediction(BaseModel):
    underlying: OptionUnderlying
    expiry: date
    spot: float
    lot_size: int
    direction: PredictionDirection
    score: float
    raw_score: float
    signal_score: float
    confidence: float = Field(description="Deprecated alias of signal_score; not a calibrated probability")
    time_modifier: float
    coverage: float
    gate_reason: GateReason
    session_status: str
    data_freshness: DataFreshness
    quote_timestamps: List[QuoteFreshness]
    contract: Optional[SuggestedContract]
    metrics: ChainMetrics
    factors: List[PredictionFactor]
    generated_at: datetime
    session_label: str
    is_expiry_day: bool
    cluster_scores: Dict[FactorCluster, ClusterScore]
    regime: RegimeSnapshot
    shadow: ShadowFeatures
    log_id: Optional[int] = None
