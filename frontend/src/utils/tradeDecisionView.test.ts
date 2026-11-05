import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import type { TradeDecision } from '../types/tradeDecision.ts';
import {
  decisionHeadline,
  decisionIconLabel,
  decisionTone,
  failedDiagnostics,
  freshnessLabel,
  secondaryDiagnostics,
} from './tradeDecisionView.ts';

function decision(partial: Partial<TradeDecision>): TradeDecision {
  return {
    status: 'NO_TRADE',
    reason: 'Waiting for a confirmed setup',
    block_code: 'WAITING_SETUP',
    underlying: 'NIFTY',
    expiry: '2026-10-27',
    session_phase: 'REGULAR',
    premarket_action: 'WAIT',
    prediction_direction: 'CALL',
    gate_reason: 'NONE',
    data_freshness: 'FRESH',
    contract_symbol: 'NIFTY27OCT2625000CE',
    manual_override_eligible: true,
    override_note: null,
    diagnostics: [
      { code: 'PREMARKET_NO_TRADE', passed: true, detail: 'WATCH' },
      { code: 'SESSION_CLOSED', passed: true, detail: 'REGULAR' },
      { code: 'FRESHNESS_UNVERIFIED', passed: true, detail: 'FRESH' },
      { code: 'WAITING_SETUP', passed: false, detail: 'Premarket WAIT' },
      { code: 'NO_CONTRACT', passed: true, detail: 'Contract present' },
      { code: 'RISK_LIMIT', passed: true, detail: 'clear' },
      { code: 'SETUP_NOT_ACTIONABLE', passed: false, detail: 'waiting' },
    ],
    disclaimer: 'not an authorization',
    ...partial,
  };
}

describe('decisionHeadline / tone / icon', () => {
  it('labels TRADE without relying on color alone', () => {
    assert.equal(decisionHeadline('TRADE'), 'TRADE');
    assert.equal(decisionIconLabel('TRADE'), 'Allowed');
    assert.equal(decisionTone('TRADE'), 'go');
  });

  it('labels NO TRADE without relying on color alone', () => {
    assert.equal(decisionHeadline('NO_TRADE'), 'NO TRADE');
    assert.equal(decisionIconLabel('NO_TRADE'), 'Blocked');
    assert.equal(decisionTone('NO_TRADE'), 'stop');
  });
});

describe('diagnostics helpers', () => {
  it('lists every failed gate', () => {
    const failed = failedDiagnostics(decision({}));
    assert.deepEqual(
      failed.map((d) => d.code),
      ['WAITING_SETUP', 'SETUP_NOT_ACTIONABLE'],
    );
  });

  it('exposes secondary failures excluding the primary block', () => {
    const secondary = secondaryDiagnostics(decision({}));
    assert.deepEqual(
      secondary.map((d) => d.code),
      ['SETUP_NOT_ACTIONABLE'],
    );
  });

  it('keeps WAIT as NO TRADE even when a contract exists', () => {
    const d = decision({});
    assert.equal(d.status, 'NO_TRADE');
    assert.equal(d.reason, 'Waiting for a confirmed setup');
    assert.equal(decisionHeadline(d.status), 'NO TRADE');
  });
});

describe('freshnessLabel', () => {
  it('renders NOT_EVALUATED without treating null as unverified', () => {
    assert.equal(freshnessLabel('NOT_EVALUATED'), 'NOT EVALUATED');
    assert.equal(freshnessLabel('FRESH'), 'FRESH');
    assert.equal(freshnessLabel(null), null);
  });
});

describe('displayed reason states', () => {
  const cases: Array<{ reason: string; status: TradeDecision['status'] }> = [
    { status: 'TRADE', reason: 'Actionable setup; all safety checks passed' },
    { status: 'NO_TRADE', reason: 'Waiting for a confirmed setup' },
    { status: 'NO_TRADE', reason: 'Premarket NO_TRADE: new entries blocked' },
    { status: 'NO_TRADE', reason: 'Exchange timestamp missing; freshness unverified' },
    { status: 'NO_TRADE', reason: 'Market session closed' },
    { status: 'NO_TRADE', reason: 'No valid option contract' },
    { status: 'NO_TRADE', reason: 'Risk limit exceeded' },
  ];

  for (const c of cases) {
    it(`renders ${c.reason}`, () => {
      const d = decision({ status: c.status, reason: c.reason, block_code: c.status === 'TRADE' ? null : 'WAITING_SETUP' });
      assert.equal(d.reason, c.reason);
      assert.equal(decisionHeadline(d.status), c.status === 'TRADE' ? 'TRADE' : 'NO TRADE');
    });
  }
});
