import type {
  DataFreshness,
  FreshnessBasis,
  OptionPrediction,
  PredictionDirection,
  QuoteFreshness,
} from '../types/prediction';

const NON_ACTIONABLE: ReadonlySet<PredictionDirection> = new Set([
  'NO_TRADE',
  'WAIT',
  'MARKET_CLOSED',
  'STALE_DATA',
  'UNKNOWN_FRESHNESS',
]);

const FRESHNESS_BASES: ReadonlySet<string> = new Set(['EXCHANGE', 'FETCH', 'UNKNOWN']);

export function isDiagnosticPrediction(prediction: Pick<OptionPrediction, 'direction' | 'contract' | 'gate_reason'>): boolean {
  if (prediction.contract != null) {
    return false;
  }
  return prediction.gate_reason !== 'NONE' || NON_ACTIONABLE.has(prediction.direction);
}

export function scoreHeading(diagnostic: boolean): string {
  return diagnostic ? 'Diagnostic score · Not actionable' : 'Signal score';
}

export function scoreCaption(diagnostic: boolean): string {
  return diagnostic ? '' : 'Uncalibrated · not a probability';
}

export function quoteRole(symbol: string): 'Spot' | 'Option' {
  if (symbol.startsWith('^') || symbol.includes('NSEI') || symbol.includes('NSEBANK')) {
    return 'Spot';
  }
  return 'Option';
}

/** Reads API `basis` (EXCHANGE | FETCH | UNKNOWN); never infer from provider or age. */
export function resolveFreshnessBasis(basis: QuoteFreshness['basis'] | null | undefined): FreshnessBasis {
  if (typeof basis === 'string' && FRESHNESS_BASES.has(basis)) {
    return basis;
  }
  return 'UNKNOWN';
}

export function formatQuoteFreshnessLine(quote: QuoteFreshness): string {
  const role = quoteRole(quote.symbol);
  const verified = quote.verified === true ? 'verified' : 'unverified';
  const freshness: DataFreshness = quote.freshness ?? 'UNKNOWN';
  const basis = resolveFreshnessBasis(quote.basis);
  const age =
    quote.age_seconds != null && basis === 'EXCHANGE'
      ? ` · exch age ${quote.age_seconds.toFixed(0)}s`
      : quote.age_seconds != null && basis === 'FETCH'
        ? ` · fetch age ${quote.age_seconds.toFixed(0)}s`
        : '';
  const when = quote.exchange_timestamp
    ? ` · exch ${new Date(quote.exchange_timestamp).toLocaleTimeString('en-IN')}`
    : quote.fetched_at
      ? ` · fetched ${new Date(quote.fetched_at).toLocaleTimeString('en-IN')}`
      : '';
  return `${role} ${quote.symbol}: ${freshness} · ${verified} · basis ${basis}${when}${age}`;
}
