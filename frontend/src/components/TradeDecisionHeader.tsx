import { useState } from 'react';
import { tradingAPI } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import type { OptionUnderlying } from '../types/options';
import type { TradeDecision } from '../types/tradeDecision';
import { apiErrorMessage } from '../utils/api-error';
import {
  decisionHeadline,
  decisionIconLabel,
  decisionTone,
  freshnessLabel,
  secondaryDiagnostics,
} from '../utils/tradeDecisionView';

const DECISION_POLL_MS = 30000;

export default function TradeDecisionHeader({
  underlying,
  expiry,
}: {
  underlying: OptionUnderlying;
  expiry: string;
}) {
  const [decision, setDecision] = useState<TradeDecision | null>(null);
  const [error, setError] = useState('');
  const [showDetails, setShowDetails] = useState(false);

  usePolling(async () => {
    try {
      const res = await tradingAPI.getDecision(underlying, expiry);
      setDecision(res.data);
      setError('');
    } catch (err) {
      // Keep the last authoritative decision so a slow refresh does not blank the header.
      setError(apiErrorMessage(err));
    }
  }, DECISION_POLL_MS, [underlying, expiry], expiry !== '');

  if (!expiry) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="card"
        style={{ marginBottom: 16, borderLeft: '4px solid var(--text-muted)' }}
      >
        <div style={{ fontWeight: 800, fontSize: '1.1rem' }}>NO TRADE</div>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: 4 }}>
          Select an expiry to evaluate the entry decision
        </div>
      </div>
    );
  }

  if (error && !decision) {
    return (
      <div
        role="alert"
        className="card"
        style={{ marginBottom: 16, borderLeft: '4px solid var(--sell)' }}
      >
        <div style={{ fontWeight: 800 }}>NO TRADE</div>
        <div style={{ fontSize: '0.85rem', marginTop: 4, fontWeight: 600 }}>
          Decision check unavailable
        </div>
        <div style={{ fontSize: '0.78rem', marginTop: 4, color: 'var(--text-muted)' }}>{error}</div>
      </div>
    );
  }

  if (!decision) {
    return (
      <div className="card" style={{ marginBottom: 16 }} role="status" aria-busy="true">
        <div className="spinner" />
      </div>
    );
  }

  const tone = decisionTone(decision.status);
  const border = tone === 'go' ? 'var(--buy)' : 'var(--sell)';
  const secondary = secondaryDiagnostics(decision);
  const freshness = freshnessLabel(decision.data_freshness);

  return (
    <div
      role="status"
      aria-live="polite"
      className="card"
      style={{ marginBottom: 16, borderLeft: `4px solid ${border}` }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <span
              style={{
                fontWeight: 900,
                fontSize: '1.6rem',
                letterSpacing: '0.04em',
                color: border,
              }}
            >
              {decisionHeadline(decision.status)}
            </span>
            <span
              aria-label={decisionIconLabel(decision.status)}
              title={decisionIconLabel(decision.status)}
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
                border: `1px solid ${border}`,
                borderRadius: 4,
                padding: '2px 8px',
              }}
            >
              {tone === 'go' ? '✓ Allowed' : '✕ Blocked'}
            </span>
          </div>
          <div style={{ fontSize: '0.95rem', marginTop: 6, fontWeight: 600 }}>
            {decision.reason}
          </div>
          {error && (
            <div style={{ fontSize: '0.78rem', marginTop: 6, color: 'var(--sell)' }}>
              Refresh delayed: {error}
            </div>
          )}
          {decision.override_note && (
            <div style={{ fontSize: '0.78rem', marginTop: 6, color: 'var(--text-muted)' }}>
              {decision.override_note}
            </div>
          )}
          {decision.manual_override_eligible && !decision.override_note && (
            <div style={{ fontSize: '0.78rem', marginTop: 6, color: 'var(--text-muted)' }}>
              A typed manual override may be submitted later; this header stays NO TRADE until
              an actionable setup and all safety checks pass.
            </div>
          )}
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ padding: '4px 10px', fontSize: '0.72rem', flexShrink: 0 }}
          onClick={() => setShowDetails((v) => !v)}
          aria-expanded={showDetails}
        >
          {showDetails ? 'Hide details' : 'Details'}
        </button>
      </div>
      {showDetails && (
        <div style={{ marginTop: 12, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
          <div style={{ marginBottom: 8 }}>{decision.disclaimer}</div>
          <div style={{ marginBottom: 6 }}>
            Session {decision.session_phase}
            {decision.premarket_action ? ` · Premarket ${decision.premarket_action}` : ''}
            {freshness ? ` · Freshness ${freshness}` : ''}
            {decision.contract_symbol ? ` · ${decision.contract_symbol}` : ''}
          </div>
          {secondary.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {secondary.map((d) => (
                <li key={d.code}>{d.code.replace(/_/g, ' ')}: {d.detail}</li>
              ))}
            </ul>
          )}
          {secondary.length === 0 && (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {decision.diagnostics.map((d) => (
                <li key={d.code}>
                  {d.passed ? 'Pass' : 'Fail'} · {d.code.replace(/_/g, ' ')}: {d.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
