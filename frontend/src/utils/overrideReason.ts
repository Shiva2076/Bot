import type { RecommendedAction } from '../types/premarket.ts';

export const OVERRIDE_REASON_MAX_LENGTH = 500;

/**
 * Prediction ADD (fromSignal) only needs a typed reason under premarket WAIT.
 * Unknown/null premarket must not force a reason and block the ADD → BUY path.
 * Non-signal orders always need a reason when entries are otherwise possible.
 */
export const requiresOverrideReason = (
  premarketAction: RecommendedAction | null,
  fromSignal: boolean,
): boolean => {
  if (premarketAction === 'NO_TRADE') {
    return false;
  }
  if (fromSignal) {
    return premarketAction === 'WAIT';
  }
  return true;
};

export const overrideReasonError = (raw: string): string | null => {
  const reason = raw.trim();
  if (reason.length === 0) return 'A manual override reason is required';
  if (reason.length > OVERRIDE_REASON_MAX_LENGTH) {
    return `Override reason must be at most ${OVERRIDE_REASON_MAX_LENGTH} characters`;
  }
  return null;
};
