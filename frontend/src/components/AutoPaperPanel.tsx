import { useState } from 'react';
import { tradingAPI } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import type { AutoPaperSignal, AutoPaperStatus } from '../types/autoPaper';
import { apiErrorMessage } from '../utils/api-error';
import { Tag } from './TradeBadges';

const POLL_MS = 30000;
const muted = { fontSize: '0.7rem', color: 'var(--text-muted)' } as const;

function outcomeColor(s: AutoPaperSignal) {
  if (s.execution_status === 'EXECUTED') return 'var(--buy)';
  if (s.eligibility_status.startsWith('REJECTED')) return 'var(--sell)';
  return 'var(--text-muted)';
}

function time(iso: string | null) {
  return iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '--';
}

/** Automatic paper-trading status: what the engine did today and why. Paper only. */
export default function AutoPaperPanel() {
  const [status, setStatus] = useState<AutoPaperStatus | null>(null);
  const [error, setError] = useState('');

  usePolling(async () => {
    try {
      setStatus((await tradingAPI.getAutoPaper()).data);
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, POLL_MS, []);

  if (error) return <div className="card" style={{ color: 'var(--sell)', fontSize: '0.8rem', marginBottom: 16 }}>{error}</div>;
  if (!status) return null;

  const c = status.config;
  return (
    <div className="card" style={{ marginBottom: 16, padding: '12px 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontWeight: 700 }}>Auto paper trading</div>
          <div style={muted}>
            {c.underlyings.join(', ')} · {c.lots} lot · entries {c.entry_start}–{c.last_entry} IST · square-off {c.square_off} ·
            max {c.max_entries_per_day}/day · paper only, no broker orders
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Tag label={status.enabled ? 'ON' : 'OFF'} color={status.enabled ? 'var(--buy)' : 'var(--text-muted)'} />
          <span style={muted}>entries today {status.entries_today} · open {status.open_auto_positions}</span>
        </div>
      </div>
      <div style={{ ...muted, marginTop: 6 }}>
        Last check {time(status.last_run_at)} ({status.session_phase}){status.last_note ? `: ${status.last_note}` : ''}
      </div>
      {status.signals_today.length > 0 && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {status.signals_today.map(s => (
            <div key={s.id} style={{ fontSize: '0.75rem', borderTop: '1px solid var(--border, #2a2f3a)', paddingTop: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <span className="mono">
                  {time(s.generated_at)} {s.direction} {s.contract_symbol ?? ''}
                  {s.entry_premium != null && ` @${s.entry_premium.toFixed(2)} SL ${s.stop_loss?.toFixed(2)} T ${s.target?.toFixed(2)}`}
                </span>
                <span style={{ color: outcomeColor(s), fontWeight: 600 }}>
                  {s.execution_status === 'EXECUTED' ? `FILLED (trade #${s.trade_id})` : s.eligibility_status}
                </span>
              </div>
              {s.rejection_reasons.length > 0 && <div style={muted}>{s.rejection_reasons.join('; ')}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
