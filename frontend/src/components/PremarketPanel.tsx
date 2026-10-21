import { useState } from 'react';
import { premarketAPI } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import type { MarketSentiment, PremarketReport, RecommendedAction } from '../types/premarket';
import { apiErrorMessage } from '../utils/api-error';
import { Tag } from './TradeBadges';

const POLL_MS = 120000;

const SENTIMENT_COLOR: Record<MarketSentiment, string> = {
  BULLISH: 'var(--buy)',
  BEARISH: 'var(--sell)',
  NEUTRAL: 'var(--text-muted)',
  INSUFFICIENT_DATA: 'var(--text-muted)',
};

const ACTION_COLOR: Record<RecommendedAction, string> = {
  WATCH: 'var(--buy)',
  WAIT: 'var(--neutral, #f59e0b)',
  NO_TRADE: 'var(--sell)',
};

const muted = { fontSize: '0.68rem', color: 'var(--text-muted)' } as const;
const formatPct = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;

export default function PremarketPanel({ compact = false }: { compact?: boolean }) {
  const [report, setReport] = useState<PremarketReport | null>(null);
  const [error, setError] = useState('');

  usePolling(async () => {
    try {
      const res = await premarketAPI.getLatest();
      setReport(res.data);
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, POLL_MS, []);

  if (error) {
    return <div className="card" style={{ color: 'var(--sell)', fontSize: '0.8rem' }}>{error}</div>;
  }
  if (!report) {
    return <div className="card" style={{ textAlign: 'center', padding: 24 }}><div className="spinner" /></div>;
  }

  const color = SENTIMENT_COLOR[report.overall_sentiment];

  if (compact) {
    return (
      <div className="card" style={{ marginBottom: 16, padding: '12px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={muted}>Pre-Market Bias</div>
            <div style={{ fontWeight: 800, color, fontSize: '1.05rem' }}>{report.overall_sentiment}</div>
          </div>
          <div>
            <div style={muted}>Heuristic conf.</div>
            <div className="mono" style={{ fontWeight: 700 }}>{report.heuristic_confidence.toFixed(0)}%</div>
          </div>
          <Tag label={report.recommended_action} color={ACTION_COLOR[report.recommended_action]} />
          <div style={muted}>
            VIX {report.india_vix.available ? `${report.india_vix.value?.toFixed(1)} (${report.india_vix.band})` : 'n/a'}
            {' · '}Gap {report.nifty_context.gap_pct !== null ? `${report.nifty_context.gap_pct >= 0 ? '+' : ''}${report.nifty_context.gap_pct.toFixed(2)}%` : 'n/a'}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="card-title">Pre-Market Analyzer</span>
        <span style={muted}>{report.session_phase} · {new Date(report.generated_at).toLocaleTimeString('en-IN')}</span>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 800, color }}>{report.overall_sentiment}</div>
        <div style={{ textAlign: 'right' }}>
          <div style={muted}>Heuristic confidence</div>
          <div className="mono" style={{ fontWeight: 800, fontSize: '1.2rem', color }}>{report.heuristic_confidence.toFixed(1)}%</div>
          <Tag label={report.recommended_action} color={ACTION_COLOR[report.recommended_action]} />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10, marginBottom: 14 }}>
        <Metric label="India VIX" value={report.india_vix.available ? `${report.india_vix.value?.toFixed(2)} · ${report.india_vix.band}` : 'Unavailable'} />
        <Metric label="NIFTY Gap" value={report.nifty_context.gap_pct !== null ? formatPct(report.nifty_context.gap_pct) : 'Unavailable'} />
        <Metric label="Breadth A/D" value={report.breadth.available ? report.breadth.advance_decline_ratio.toFixed(2) : 'Unavailable'} />
        <Metric label="GIFT Nifty" value={report.gift_nifty.available && report.gift_nifty.change_pct !== null ? formatPct(report.gift_nifty.change_pct) : 'Unavailable'} />
      </div>

      <div style={{ ...muted, marginBottom: 8 }}>Global tape</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
        {report.global_markets.map(m => (
          <span key={m.symbol} className="mono" style={{ fontSize: '0.72rem', color: SENTIMENT_COLOR[m.sentiment] }}>
            {m.name} {formatPct(m.change_pct)}
          </span>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        <ListBlock title="Strongest sectors" items={report.strongest_sectors.map(s => `${s.name} ${formatPct(s.change_pct)}`)} />
        <ListBlock title="Weakest sectors" items={report.weakest_sectors.map(s => `${s.name} ${formatPct(s.change_pct)}`)} />
      </div>

      <ListBlock title="Why this call" items={report.reasons.slice(0, 6)} />
      <ListBlock title="Key risks" items={report.key_risks.slice(0, 4)} />

      {report.data_quality_warnings.length > 0 && (
        <div style={{ marginTop: 10, fontSize: '0.72rem', color: 'var(--neutral, #f59e0b)' }}>
          {report.data_quality_warnings[0]}
        </div>
      )}
      <div style={{ ...muted, marginTop: 10 }}>{report.score_note}</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={muted}>{label}</div>
      <div className="mono" style={{ fontWeight: 700, fontSize: '0.85rem' }}>{value}</div>
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ ...muted, marginBottom: 4 }}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: 16, fontSize: '0.75rem', color: 'var(--text-secondary, var(--text-muted))' }}>
        {items.map(item => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
