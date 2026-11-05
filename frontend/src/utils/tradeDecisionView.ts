import type { DataFreshness } from '../types/prediction.ts';
import type { TradeDecision, TradeDecisionStatus } from '../types/tradeDecision.ts';

/** Display helpers only — never compute TRADE / NO_TRADE on the client. */

export function decisionHeadline(status: TradeDecisionStatus): string {
  return status === 'TRADE' ? 'TRADE' : 'NO TRADE';
}

export function freshnessLabel(freshness: DataFreshness | null): string | null {
  if (freshness == null) {
    return null;
  }
  return freshness === 'NOT_EVALUATED' ? 'NOT EVALUATED' : freshness;
}

export function decisionIconLabel(status: TradeDecisionStatus): string {
  return status === 'TRADE' ? 'Allowed' : 'Blocked';
}

export function decisionTone(status: TradeDecisionStatus): 'go' | 'stop' {
  return status === 'TRADE' ? 'go' : 'stop';
}

export function failedDiagnostics(decision: TradeDecision): TradeDecision['diagnostics'] {
  return decision.diagnostics.filter((d) => !d.passed);
}

export function secondaryDiagnostics(decision: TradeDecision): TradeDecision['diagnostics'] {
  return failedDiagnostics(decision).filter((d) => d.code !== decision.block_code);
}
