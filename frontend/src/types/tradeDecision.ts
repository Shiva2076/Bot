import type { OptionUnderlying } from './options';
import type { DataFreshness, GateReason, PredictionDirection } from './prediction';
import type { RecommendedAction } from './premarket';

export type TradeDecisionStatus = 'TRADE' | 'NO_TRADE';

export type TradeDecisionBlockCode =
  | 'PREMARKET_NO_TRADE'
  | 'SESSION_CLOSED'
  | 'FRESHNESS_UNVERIFIED'
  | 'WAITING_SETUP'
  | 'NO_CONTRACT'
  | 'RISK_LIMIT'
  | 'SETUP_NOT_ACTIONABLE';

export interface TradeDecisionGateDiagnostic {
  code: TradeDecisionBlockCode;
  passed: boolean;
  detail: string;
}

export interface TradeDecision {
  status: TradeDecisionStatus;
  reason: string;
  block_code: TradeDecisionBlockCode | null;
  underlying: OptionUnderlying;
  expiry: string;
  session_phase: string;
  premarket_action: RecommendedAction | null;
  prediction_direction: PredictionDirection | null;
  gate_reason: GateReason | null;
  data_freshness: DataFreshness | null;
  contract_symbol: string | null;
  manual_override_eligible: boolean;
  override_note: string | null;
  diagnostics: TradeDecisionGateDiagnostic[];
  disclaimer: string;
}
