import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { OVERRIDE_REASON_MAX_LENGTH, overrideReasonError, requiresOverrideReason } from './overrideReason.ts';

describe('requiresOverrideReason', () => {
  it('does not require a reason for prediction ADD under WATCH or unknown premarket', () => {
    assert.equal(requiresOverrideReason('WATCH', true), false);
    assert.equal(requiresOverrideReason(null, true), false);
  });

  it('requires a reason for prediction ADD only under WAIT', () => {
    assert.equal(requiresOverrideReason('WAIT', true), true);
  });

  it('requires a reason for non-signal orders except NO_TRADE (unoverridable)', () => {
    assert.equal(requiresOverrideReason('WATCH', false), true);
    assert.equal(requiresOverrideReason('WAIT', false), true);
    assert.equal(requiresOverrideReason(null, false), true);
    assert.equal(requiresOverrideReason('NO_TRADE', true), false);
    assert.equal(requiresOverrideReason('NO_TRADE', false), false);
  });
});

describe('overrideReasonError', () => {
  it('rejects empty and whitespace-only reasons', () => {
    assert.notEqual(overrideReasonError(''), null);
    assert.notEqual(overrideReasonError('   \n '), null);
  });

  it('enforces the max length after trimming', () => {
    assert.equal(overrideReasonError(`  ${'x'.repeat(OVERRIDE_REASON_MAX_LENGTH)}  `), null);
    assert.notEqual(overrideReasonError('x'.repeat(OVERRIDE_REASON_MAX_LENGTH + 1)), null);
  });

  it('accepts a normal reason', () => {
    assert.equal(overrideReasonError('Breadth divergence'), null);
  });
});
