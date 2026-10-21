import { useEffect, useState } from 'react';
import { optionsAPI } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import type { OptionUnderlying } from '../types/options';
import type {
  FactorBias,
  FactorStatus,
  OptionPrediction,
  PredictionDirection,
  SuggestedContract,
} from '../types/prediction';
import { apiErrorMessage } from '../utils/api-error';
import {
  formatQuoteFreshnessLine,
  isDiagnosticPrediction,
  resolveFreshnessBasis,
  scoreCaption,
  scoreHeading,
} from '../utils/predictionPanelView';
import { Tag } from './TradeBadges';

const PREDICTION_POLL_MS = 120000;

const DIRECTION_LABELS: Record<PredictionDirection, string> = {
  CALL: 'BUY CALL',
  PUT: 'BUY PUT',
  NO_TRADE: 'NO TRADE',
  WAIT: 'WAIT',
  MARKET_CLOSED: 'MARKET CLOSED',
  STALE_DATA: 'STALE DATA',
  UNKNOWN_FRESHNESS: 'UNKNOWN FRESHNESS',
};
const DIRECTION_COLORS: Record<PredictionDirection, string> = {
  CALL: 'var(--buy)',
  PUT: 'var(--sell)',
  NO_TRADE: 'var(--text-muted)',
  WAIT: 'var(--text-muted)',
  MARKET_CLOSED: 'var(--text-muted)',
  STALE_DATA: 'var(--sell)',
  UNKNOWN_FRESHNESS: 'var(--sell)',
};
const BIAS_COLORS: Record<FactorBias, string> = {
  BULLISH: 'var(--buy)',
  BEARISH: 'var(--sell)',
  NEUTRAL: 'var(--text-muted)',
};

const labelStyle = { fontSize: '0.68rem', color: 'var(--text-muted)' } as const;
const formatInr = (value: number) => `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={labelStyle}>{label}</div>
      <div className="mono" style={{ fontWeight: 700, fontSize: '0.85rem' }}>{value}</div>
    </div>
  );
}

function isInactive(status: FactorStatus) {
  return status === 'DISABLED' || status === 'UNAVAILABLE';
}

export interface PredictionAddRequest {
  contract: SuggestedContract;
  lotSize: number;
  underlying: OptionUnderlying;
}

export default function PredictionPanel({
  underlying,
  expiry,
  onAdd,
}: {
  underlying: OptionUnderlying;
  expiry: string;
  onAdd: (request: PredictionAddRequest) => void;
}) {
  const [prediction, setPrediction] = useState<OptionPrediction | null>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => { setPrediction(null); }, [underlying, expiry]);

  usePolling(async () => {
    try {
      const res = await optionsAPI.getPrediction(underlying, expiry);
      setPrediction(res.data);
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, PREDICTION_POLL_MS, [underlying, expiry], expiry !== '');

  const refresh = async () => {
    if (!expiry || refreshing) return;
    setRefreshing(true);
    try {
      const res = await optionsAPI.getPrediction(underlying, expiry, true);
      setPrediction(res.data);
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setRefreshing(false);
    }
  };

  const color = prediction ? DIRECTION_COLORS[prediction.direction] : 'var(--text-muted)';
  const contract = prediction?.contract ?? null;
  const diagnostic = prediction ? isDiagnosticPrediction(prediction) : false;

  return (
    <div className="card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span className="card-title">Prediction · {underlying}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {prediction && (
            <span style={labelStyle}>
              Predicted {new Date(prediction.generated_at).toLocaleTimeString('en-IN')} · {prediction.session_status}
            </span>
          )}
          <button
            type="button"
            className="btn btn-ghost"
            disabled={refreshing || expiry === ''}
            onClick={refresh}
            style={{ padding: '2px 10px', fontSize: '0.7rem' }}
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
      {error && <div style={{ color: 'var(--sell)', fontSize: '0.78rem', marginBottom: 10 }}>{error}</div>}
      {!prediction ? (
        <div style={{ padding: 30, textAlign: 'center' }}><div className="spinner" /></div>
      ) : (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14, gap: 12 }}>
            <span style={{ fontSize: '1.4rem', fontWeight: 800, color }}>{DIRECTION_LABELS[prediction.direction]}</span>
            <div
              style={{
                textAlign: 'right',
                padding: diagnostic ? '8px 10px' : 0,
                borderRadius: 6,
                background: diagnostic ? 'var(--bg-secondary, rgba(127,127,127,0.12))' : 'transparent',
                border: diagnostic ? '1px dashed var(--text-muted)' : 'none',
                minWidth: 140,
              }}
            >
              <div style={{ ...labelStyle, fontWeight: diagnostic ? 600 : 400 }}>
                {scoreHeading(diagnostic)}
              </div>
              <div
                className="mono"
                style={{
                  fontWeight: diagnostic ? 600 : 800,
                  fontSize: diagnostic ? '0.95rem' : '1.1rem',
                  color: diagnostic ? 'var(--text-muted)' : color,
                }}
              >
                {prediction.signal_score.toFixed(1)}
              </div>
              {scoreCaption(diagnostic) && (
                <div style={labelStyle}>{scoreCaption(diagnostic)}</div>
              )}
              <div style={{ ...labelStyle, marginTop: 4 }}>
                raw {prediction.raw_score.toFixed(3)} · time ×{prediction.time_modifier.toFixed(2)} · cov {(prediction.coverage * 100).toFixed(0)}%
              </div>
            </div>
          </div>

          {prediction.gate_reason !== 'NONE' && (
            <div style={{ ...labelStyle, marginBottom: 10, color: 'var(--sell)' }}>
              Gate: {prediction.gate_reason.replace(/_/g, ' ')} · freshness {prediction.data_freshness}
            </div>
          )}

          {prediction.quote_timestamps.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ ...labelStyle, marginBottom: 4 }}>Quote freshness</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {prediction.quote_timestamps.map(q => (
                  <div
                    key={`${q.symbol}-${resolveFreshnessBasis(q.basis)}-${q.freshness ?? 'UNKNOWN'}`}
                    className="mono"
                    style={{ ...labelStyle, color: 'var(--text-primary)' }}
                  >
                    {formatQuoteFreshnessLine(q)}
                  </div>
                ))}
              </div>
            </div>
          )}

          {contract ? (
            <div style={{ border: `1px solid ${color}`, borderRadius: 8, padding: 12, marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{contract.quote.display_name}</div>
                <button
                  type="button"
                  className="btn btn-buy"
                  style={{ padding: '4px 14px', fontSize: '0.75rem', fontWeight: 700 }}
                  onClick={() => onAdd({ contract, lotSize: prediction.lot_size, underlying })}
                >
                  ADD
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 10 }}>
                <Metric label="Entry" value={formatInr(contract.levels.entry)} />
                <Metric label="Stop Loss" value={formatInr(contract.levels.stop_loss)} />
                <Metric label="Target" value={formatInr(contract.levels.target)} />
              </div>
              <div style={labelStyle}>
                1 lot ({prediction.lot_size} qty) ≈ <span className="mono" style={{ color: 'var(--text-primary)' }}>{formatInr(contract.levels.entry * prediction.lot_size)}</span>
              </div>
            </div>
          ) : (
            <div style={{ ...labelStyle, marginBottom: 14 }}>
              No actionable contract.
              {diagnostic ? ' Diagnostic score · Not actionable.' : ' Signal score is not a calibrated probability of success.'}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
            <Metric label="Near-spot PCR" value={(prediction.metrics.near_spot_pcr ?? prediction.metrics.put_call_ratio).toFixed(2)} />
            <Metric label="Max Pain" value={prediction.metrics.max_pain.toFixed(0)} />
            <Metric label="Support (Put OI)" value={prediction.metrics.put_wall.toFixed(0)} />
            <Metric label="Resistance (Call OI)" value={prediction.metrics.call_wall.toFixed(0)} />
          </div>

          <div style={{ ...labelStyle, marginBottom: 6 }}>Factors</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {prediction.factors.map(f => {
              const inactive = isInactive(f.status);
              return (
                <div key={f.name} style={{ fontSize: '0.75rem', opacity: inactive ? 0.45 : 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 600 }}>{f.name}</span>
                    {inactive ? (
                      <Tag label={f.status} color="var(--text-muted)" />
                    ) : (
                      <Tag label={f.bias} color={BIAS_COLORS[f.bias]} />
                    )}
                  </div>
                  <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>{f.detail}</div>
                  <div style={{ ...labelStyle, marginTop: 2 }}>
                    w={f.effective_weight.toFixed(3)} · contrib {f.contribution_pct.toFixed(1)}% · {f.cluster}
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 12 }}>
            Paper-mode rule-based prediction. Not financial advice.
          </div>
        </>
      )}
    </div>
  );
}
