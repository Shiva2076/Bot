import type { OptionQuote, OptionUnderlying } from './options';

export type PredictionDirection =
  | 'CALL'
  | 'PUT'
  | 'NO_TRADE'
  | 'WAIT'
  | 'MARKET_CLOSED'
  | 'STALE_DATA'
  | 'UNKNOWN_FRESHNESS';
export type FactorBias = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type FactorCluster = 'TREND' | 'LEVELS' | 'OPTIONS' | 'FUTURES_FLOW' | 'CONTEXT' | 'AGENTS' | 'REGIME';
export type FactorStatus = 'ACTIVE' | 'UNAVAILABLE' | 'DISABLED';
export type RegimeLabel = 'TRENDING' | 'RANGE' | 'TRANSITION' | 'VOLATILE' | 'UNKNOWN';
export type GateReason =
  | 'NONE'
  | 'MARKET_CLOSED'
  | 'STALE_DATA'
  | 'UNKNOWN_FRESHNESS'
  | 'MTF_CONFLICT'
  | 'CLUSTER_DISAGREEMENT'
  | 'LOW_COVERAGE'
  | 'PREMARKET_WAIT'
  | 'INVALID_DATA'
  | 'LOW_SIGNAL_SCORE'
  | 'EXPIRY_PRE_CLOSE';
export type DataFreshness = 'FRESH' | 'STALE' | 'UNKNOWN' | 'MARKET_CLOSED';
export type FreshnessBasis = 'EXCHANGE' | 'FETCH' | 'UNKNOWN';

export interface PredictionFactor {
  name: string;
  bias: FactorBias;
  score: number;
  weight: number;
  detail: string;
  cluster: FactorCluster;
  status: FactorStatus;
  contribution: number;
  contribution_pct: number;
  effective_weight: number;
}

export interface ClusterScore {
  score: number | null;
  active_factors: number;
  total_factors: number;
  contribution: number;
  contribution_pct: number;
}

export interface RegimeSnapshot {
  label: RegimeLabel;
  adx: number | null;
  vix: number | null;
  vix_change_pct: number | null;
  atm_iv: number | null;
  adx_multiplier: number;
}

export interface QuoteFreshness {
  symbol: string;
  exchange_timestamp: string | null;
  fetched_at: string | null;
  quoted_at: string | null;
  age_seconds: number | null;
  provider: string | null;
  freshness: DataFreshness;
  /** Timestamp basis from API: EXCHANGE | FETCH | UNKNOWN. Absent/invalid → treat as UNKNOWN in UI. */
  basis?: FreshnessBasis | null;
  verified: boolean;
}

export interface ChainMetrics {
  put_call_ratio: number;
  max_pain: number;
  call_wall: number;
  put_wall: number;
  total_call_oi: number;
  total_put_oi: number;
  near_spot_pcr?: number | null;
}

export interface PremiumLevels {
  entry: number;
  stop_loss: number;
  target: number;
}

export interface SuggestedContract {
  strike: number;
  option_type: 'CE' | 'PE';
  quote: OptionQuote;
  levels: PremiumLevels;
}

export type StructureBias = 'BULLISH' | 'BEARISH' | 'RANGE' | 'UNKNOWN';
export type ChartSetup =
  | 'NONE'
  | 'SUPPORT_BREAKDOWN_RETEST'
  | 'RESISTANCE_BREAKOUT_RETEST'
  | 'LIQUIDITY_SWEEP_REVERSAL'
  | 'RANGE_COMPRESSION'
  | 'FVG_RETEST'
  | 'BREAK_OF_STRUCTURE'
  | 'CHANGE_OF_CHARACTER'
  | 'DOUBLE_TOP'
  | 'DOUBLE_BOTTOM'
  | 'CHANNEL';
export type ChartLevelKind =
  | 'PDH'
  | 'PDL'
  | 'PDC'
  | 'OPENING_GAP'
  | 'SESSION_HIGH'
  | 'SESSION_LOW'
  | 'SWING_HIGH'
  | 'SWING_LOW'
  | 'FVG_TOP'
  | 'FVG_BOTTOM'
  | 'BOS'
  | 'CHOCH'
  | 'NECKLINE'
  | 'TRENDLINE'
  | 'CHANNEL'
  | 'INVALIDATION';
export type ChartActionHint = 'CALL' | 'PUT' | 'WAIT';
export type ChartPatternStatus = 'NONE' | 'POTENTIAL' | 'CONFIRMED' | 'FAILED' | 'UNCERTAIN';
export type ChartAnnotationCategory = 'LEVELS' | 'ZONES' | 'FVG' | 'TRENDLINES' | 'PATTERNS' | 'SCENARIOS';
export type ChartProjectionKind =
  | 'CHANNEL_UPPER'
  | 'CHANNEL_LOWER'
  | 'MEASURED_MOVE'
  | 'BREAKOUT_PATH'
  | 'TARGET_ZONE'
  | 'PATTERN_LABEL';
export type ChartProjectionSide = 'BULLISH' | 'BEARISH' | 'NEUTRAL';

export interface ChartLevel {
  kind: ChartLevelKind;
  price: number;
  source: string;
}

export interface ChartAnnotation {
  category: ChartAnnotationCategory;
  kind: string;
  price?: number | null;
  price_low?: number | null;
  price_high?: number | null;
  time_start?: number | null;
  time_end?: number | null;
  source: string;
  status: ChartPatternStatus;
  label: string;
}

export interface ChartProjection {
  kind: ChartProjectionKind;
  time_start: number;
  time_end: number;
  price_start: number;
  price_end: number;
  price_low?: number | null;
  price_high?: number | null;
  label: string;
  side: ChartProjectionSide;
  status: ChartPatternStatus;
  evidence: string;
}

export interface ChartPatternHit {
  pattern: string;
  status: ChartPatternStatus;
  bias: StructureBias;
  level?: number | null;
  invalidation?: number | null;
  confirmation?: string | null;
  evidence: string;
  time?: number | null;
}

export interface ChartScenario {
  side: 'BULLISH' | 'BEARISH' | 'WAIT';
  summary: string;
  confirmation?: string | null;
  invalidation?: string | null;
  invalidation_price?: number | null;
}

export interface ChartDataQuality {
  ok: boolean;
  ordered: boolean;
  duplicate_bars: number;
  gap_count: number;
  detail: string;
}

export interface ChartAnalysisReport {
  structure: StructureBias;
  pattern_status: ChartPatternStatus;
  primary_pattern?: string | null;
  evidence: string[];
  bullish: ChartScenario;
  bearish: ChartScenario;
  wait: ChartScenario;
  key_supports: number[];
  key_resistances: number[];
  data_quality: ChartDataQuality;
  as_of: string;
  narrative?: string | null;
  probability?: number | null;
  detail: string;
}

export interface ChartStructureFeatures {
  as_of: string;
  interval_5m_bars: number;
  interval_15m_bars: number;
  structure_5m: StructureBias;
  structure_15m: StructureBias;
  setup: ChartSetup;
  bias: StructureBias;
  action_hint: ChartActionHint;
  key_levels: ChartLevel[];
  evidence: string[];
  trigger: string | null;
  invalidation_price: number | null;
  invalidation_rule: string | null;
  probability: number | null;
  opening_gap_points: number | null;
  data_ok: boolean;
  detail: string;
  annotations?: ChartAnnotation[];
  patterns?: ChartPatternHit[];
  projections?: ChartProjection[];
  report?: ChartAnalysisReport | null;
  data_quality?: ChartDataQuality | null;
}

export interface ChainShadowFeatures {
  strike_window: number;
  near_call_oi: number;
  near_put_oi: number;
  near_spot_pcr: number | null;
  atm_iv: number | null;
  iv_skew_25d: number | null;
  gex_per_1pct: number | null;
  quotes_with_iv: number;
  quotes_total: number;
}

export interface ShadowFeatures {
  chain: ChainShadowFeatures;
  futures?: unknown | null;
  chart?: ChartStructureFeatures | null;
}

export interface OptionPrediction {
  underlying: OptionUnderlying;
  expiry: string;
  spot: number;
  lot_size: number;
  direction: PredictionDirection;
  score: number;
  raw_score: number;
  signal_score: number;
  /** @deprecated alias of signal_score */
  confidence: number;
  time_modifier: number;
  coverage: number;
  gate_reason: GateReason;
  session_status: string;
  data_freshness: DataFreshness;
  quote_timestamps: QuoteFreshness[];
  contract: SuggestedContract | null;
  metrics: ChainMetrics;
  factors: PredictionFactor[];
  generated_at: string;
  session_label: string;
  is_expiry_day: boolean;
  cluster_scores: Partial<Record<FactorCluster, ClusterScore>>;
  regime: RegimeSnapshot;
  shadow?: ShadowFeatures | null;
  log_id?: number | null;
}
