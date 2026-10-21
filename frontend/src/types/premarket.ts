export type MarketSentiment = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'INSUFFICIENT_DATA';
export type RecommendedAction = 'WATCH' | 'WAIT' | 'NO_TRADE';
export type VolatilityBand = 'LOW' | 'MODERATE' | 'HIGH' | 'UNKNOWN';

export interface IndexMove {
  symbol: string;
  name: string;
  last: number;
  change_pct: number;
  sentiment: MarketSentiment;
  timestamp: string;
  source: string;
}

export interface GiftNiftySnapshot {
  available: boolean;
  last: number | null;
  change_pct: number | null;
  sentiment: MarketSentiment;
  timestamp: string | null;
  source: string | null;
  warning: string | null;
}

export interface IndiaVixSnapshot {
  available: boolean;
  value: number | null;
  change_pct: number | null;
  band: VolatilityBand;
  trend: string;
  timestamp: string | null;
  source: string | null;
  warning: string | null;
}

export interface BreadthSnapshot {
  available: boolean;
  advancing: number;
  declining: number;
  unchanged: number;
  advance_decline_ratio: number;
  advancing_pct: number;
  session_label: string;
  timestamp: string | null;
  source: string | null;
  warning: string | null;
}

export interface NiftyOpeningContext {
  available: boolean;
  previous_close: number | null;
  last: number | null;
  previous_high: number | null;
  previous_low: number | null;
  gap_pct: number | null;
  support: number | null;
  resistance: number | null;
  session_phase: string;
  timestamp: string | null;
  source: string | null;
  warning: string | null;
}

export interface SectorSnapshot {
  name: string;
  change_pct: number;
  status: string;
}

export interface PremarketFactor {
  name: string;
  sentiment: MarketSentiment;
  score: number;
  weight: number;
  included: boolean;
  detail: string;
}

export interface PremarketReport {
  report_date: string;
  generated_at: string;
  session_phase: string;
  is_trading_day: boolean;
  overall_sentiment: MarketSentiment;
  heuristic_confidence: number;
  directional_score: number;
  recommended_action: RecommendedAction;
  global_markets: IndexMove[];
  gift_nifty: GiftNiftySnapshot;
  india_vix: IndiaVixSnapshot;
  breadth: BreadthSnapshot;
  nifty_context: NiftyOpeningContext;
  strongest_sectors: SectorSnapshot[];
  weakest_sectors: SectorSnapshot[];
  factors: PremarketFactor[];
  excluded_indicators: string[];
  bullish_scenarios: string[];
  bearish_scenarios: string[];
  key_risks: string[];
  upcoming_events: string[];
  reasons: string[];
  data_quality_warnings: string[];
  score_note: string;
}
