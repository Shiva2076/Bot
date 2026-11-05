import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import type { QuoteFreshness } from '../types/prediction.ts';
import {
  formatPredictionSnapshotLabel,
  formatQuoteFreshnessLine,
  isDiagnosticPrediction,
  isPredictionSnapshotStale,
  predictionSnapshotAgeSeconds,
  quoteRole,
  resolveFreshnessBasis,
  scoreHeading,
} from './predictionPanelView.ts';

describe('isDiagnosticPrediction', () => {
  it('marks gated directions without a contract as diagnostic', () => {
    for (const direction of ['MARKET_CLOSED', 'STALE_DATA', 'UNKNOWN_FRESHNESS', 'WAIT', 'NO_TRADE'] as const) {
      assert.equal(
        isDiagnosticPrediction({ direction, contract: null, gate_reason: 'NONE' }),
        true,
        direction,
      );
    }
  });

  it('marks non-NONE gate without contract as diagnostic', () => {
    assert.equal(
      isDiagnosticPrediction({ direction: 'CALL', contract: null, gate_reason: 'LOW_SIGNAL_SCORE' }),
      true,
    );
  });

  it('does not mark actionable CALL/PUT with a contract as diagnostic', () => {
    assert.equal(
      isDiagnosticPrediction({
        direction: 'CALL',
        contract: {} as never,
        gate_reason: 'NONE',
      }),
      false,
    );
  });
});

describe('scoreHeading', () => {
  it('uses diagnostic copy when gated', () => {
    assert.equal(scoreHeading(true), 'Diagnostic score · Not actionable');
    assert.equal(scoreHeading(false), 'Signal score');
  });
});

describe('resolveFreshnessBasis', () => {
  it('falls back to UNKNOWN when basis is absent or invalid', () => {
    assert.equal(resolveFreshnessBasis(undefined), 'UNKNOWN');
    assert.equal(resolveFreshnessBasis(null), 'UNKNOWN');
    assert.equal(resolveFreshnessBasis('' as never), 'UNKNOWN');
    assert.equal(resolveFreshnessBasis('FETCH'), 'FETCH');
    assert.equal(resolveFreshnessBasis('EXCHANGE'), 'EXCHANGE');
    assert.equal(resolveFreshnessBasis('UNKNOWN'), 'UNKNOWN');
  });
});

describe('formatQuoteFreshnessLine', () => {
  it('shows basis UNKNOWN instead of the string undefined when field is missing', () => {
    const spot = {
      symbol: 'NSEI',
      exchange_timestamp: null,
      fetched_at: '2026-03-20T10:00:00+05:30',
      quoted_at: null,
      age_seconds: 12,
      provider: 'angel',
      freshness: 'UNKNOWN',
      verified: false,
    } as QuoteFreshness;
    const line = formatQuoteFreshnessLine(spot);
    assert.match(line, /basis UNKNOWN/);
    assert.doesNotMatch(line, /undefined/);
  });

  it('renders API freshness, verified, and basis without inferring verification', () => {
    const spot: QuoteFreshness = {
      symbol: '^NSEI',
      exchange_timestamp: null,
      fetched_at: '2026-03-20T10:00:00+05:30',
      quoted_at: null,
      age_seconds: 12,
      provider: 'angel',
      freshness: 'UNKNOWN',
      basis: 'FETCH',
      verified: false,
    };
    const line = formatQuoteFreshnessLine(spot);
    assert.match(line, /^Spot \^NSEI:/);
    assert.match(line, /UNKNOWN/);
    assert.match(line, / · unverified · /);
    assert.match(line, /basis FETCH/);
    assert.doesNotMatch(line, / · verified · /);
  });

  it('labels option quotes separately from spot', () => {
    assert.equal(quoteRole('NIFTY26MAR25000CE'), 'Option');
    const option: QuoteFreshness = {
      symbol: 'NIFTY26MAR25000CE',
      exchange_timestamp: '2026-03-20T10:00:00+05:30',
      fetched_at: '2026-03-20T10:00:01+05:30',
      quoted_at: '2026-03-20T10:00:00+05:30',
      age_seconds: 5,
      provider: 'angel',
      freshness: 'FRESH',
      basis: 'EXCHANGE',
      verified: true,
    };
    const line = formatQuoteFreshnessLine(option);
    assert.match(line, /^Option NIFTY26MAR25000CE:/);
    assert.match(line, /FRESH · verified · basis EXCHANGE/);
  });
});

describe('prediction snapshot age', () => {
  const generatedAt = '2026-10-23T06:02:52.000Z';
  const nowMs = Date.parse('2026-10-23T06:03:22.000Z');

  it('computes non-negative age in seconds', () => {
    assert.equal(predictionSnapshotAgeSeconds(generatedAt, nowMs), 30);
    assert.equal(predictionSnapshotAgeSeconds(generatedAt, Date.parse(generatedAt) - 5000), 0);
    assert.equal(predictionSnapshotAgeSeconds('not-a-date', nowMs), null);
  });

  it('flags stale snapshots past the refresh budget', () => {
    assert.equal(isPredictionSnapshotStale(30, 90), false);
    assert.equal(isPredictionSnapshotStale(91, 90), true);
    assert.equal(isPredictionSnapshotStale(null, 90), false);
  });

  it('includes relative age in the header label', () => {
    assert.match(
      formatPredictionSnapshotLabel(generatedAt, 'REGULAR', nowMs),
      /REGULAR · 30s ago$/,
    );
    assert.match(
      formatPredictionSnapshotLabel(generatedAt, 'REGULAR', nowMs + 120_000),
      /REGULAR · 2m ago$/,
    );
  });
});
