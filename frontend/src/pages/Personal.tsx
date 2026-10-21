import { useEffect, useState } from 'react';
import { personalAPI, tradingAPI } from '../api/client';
import { PnlText, Tag } from '../components/TradeBadges';
import type { DailyTradeSummary, PersonalHistory, PersonalTrade } from '../types/personal';
import { apiErrorMessage } from '../utils/api-error';

const REFRESH_INTERVAL_MS = 15000;

const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });

function OpenPositions({ positions, onExit }: { positions: PersonalTrade[]; onExit: (id: number) => void }) {
  return (
    <div className="card" style={{ marginBottom: 20, padding: 0 }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
        <span className="card-title">Open Positions · Live P&L ({positions.length})</span>
      </div>
      {positions.length === 0 ? (
        <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)' }}>No open positions.</div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Stock</th>
                <th>Entry Time</th>
                <th style={{ textAlign: 'right' }}>Qty</th>
                <th style={{ textAlign: 'right' }}>Entry</th>
                <th style={{ textAlign: 'right' }}>LTP</th>
                <th style={{ textAlign: 'right' }}>Unrealized P&L</th>
                <th style={{ textAlign: 'right' }}>Exit</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => (
                <tr key={p.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{p.symbol.replace('.NS', '')}</div>
                    <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                      <Tag label={p.action} color={p.action === 'BUY' ? 'var(--buy)' : 'var(--sell)'} />
                      <Tag label={p.trade_type} color="var(--text-muted)" />
                    </div>
                  </td>
                  <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{new Date(p.entry_time).toLocaleString('en-IN')}</td>
                  <td style={{ textAlign: 'right' }} className="mono">{p.quantity}</td>
                  <td style={{ textAlign: 'right' }} className="mono">₹{p.entry_price.toFixed(2)}</td>
                  <td style={{ textAlign: 'right' }} className="mono">{p.current_price !== null ? `₹${p.current_price.toFixed(2)}` : '--'}</td>
                  <td style={{ textAlign: 'right' }}><PnlText value={p.pnl} pct={p.pnl_pct} /></td>
                  <td style={{ textAlign: 'right' }}>
                    {p.trade_type === 'MANUAL'
                      ? <button className="btn btn-sell" style={{ padding: '4px 10px', fontSize: '0.72rem' }} onClick={() => onExit(p.id)}>Exit at Market</button>
                      : <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Close from Portfolio</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DayCard({ day }: { day: DailyTradeSummary }) {
  const dayPnl = day.realized_pnl + day.unrealized_pnl;
  return (
    <div className="card" style={{ marginBottom: 16, padding: 0, borderLeft: `3px solid ${dayPnl >= 0 ? 'var(--buy)' : 'var(--sell)'}` }}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontWeight: 700 }}>
            {new Date(day.trade_date).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            {day.entries} entries · {day.exits} exits · {day.wins}W / {day.losses}L
          </div>
        </div>
        <div style={{ display: 'flex', gap: 20, fontSize: '0.78rem' }}>
          <div>Realized: <PnlText value={day.realized_pnl} /></div>
          <div>Unrealized: <PnlText value={day.unrealized_pnl} /></div>
          <div>Day P&L: <PnlText value={dayPnl} /></div>
        </div>
      </div>
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Entry Time</th>
              <th>Stock</th>
              <th>Side</th>
              <th>Type</th>
              <th style={{ textAlign: 'right' }}>Qty</th>
              <th style={{ textAlign: 'right' }}>Entry</th>
              <th>Exit Time</th>
              <th style={{ textAlign: 'right' }}>Exit / LTP</th>
              <th style={{ textAlign: 'right' }}>P&L</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {day.trades.map(t => (
              <tr key={t.id}>
                <td className="mono">{formatTime(t.entry_time)}</td>
                <td style={{ fontWeight: 600 }}>{t.symbol.replace('.NS', '')}</td>
                <td><Tag label={t.action} color={t.action === 'BUY' ? 'var(--buy)' : 'var(--sell)'} /></td>
                <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{t.trade_type}</td>
                <td style={{ textAlign: 'right' }} className="mono">{t.quantity}</td>
                <td style={{ textAlign: 'right' }} className="mono">₹{t.entry_price.toFixed(2)}</td>
                <td className="mono">{t.exit_time ? formatTime(t.exit_time) : '--'}</td>
                <td style={{ textAlign: 'right' }} className="mono">{t.current_price !== null ? `₹${t.current_price.toFixed(2)}` : '--'}</td>
                <td style={{ textAlign: 'right' }}><PnlText value={t.pnl} pct={t.pnl_pct} /></td>
                <td><Tag label={t.status === 'OPEN' ? 'OPEN' : t.exit_reason ?? 'CLOSED'} color={t.status === 'OPEN' ? 'var(--amber)' : 'var(--text-muted)'} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Personal() {
  const [history, setHistory] = useState<PersonalHistory | null>(null);
  const [error, setError] = useState('');

  const fetchHistory = async () => {
    try {
      const res = await personalAPI.getHistory();
      setHistory(res.data);
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  };

  const exitPosition = async (id: number) => {
    try {
      await tradingAPI.exitPosition(id);
      fetchHistory();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  };

  useEffect(() => {
    fetchHistory();
    const timer = setInterval(fetchHistory, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  if (!history && !error) return <div className="loading-screen"><div className="spinner" /></div>;

  const summary = history?.summary;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Personal</h1>
        <p className="page-subtitle">
          Day-wise intraday entries &amp; exits with live portfolio P&L
          {history && ` · Updated ${new Date(history.as_of).toLocaleTimeString('en-IN')}`}
        </p>
      </div>

      {error && <div className="card" style={{ marginBottom: 20, color: 'var(--sell)' }}>{error}</div>}

      {summary && (
        <div className="stats-row">
          <div className="stat-card">
            <div className="stat-label">Total P&L</div>
            <div className="stat-value"><PnlText value={summary.total_pnl} /></div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Today's P&L</div>
            <div className="stat-value"><PnlText value={summary.today_pnl} /></div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Realized</div>
            <div className="stat-value"><PnlText value={summary.realized_pnl} /></div>
            <div className="stat-sub">{summary.closed_trades} closed trades</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Unrealized (Live)</div>
            <div className="stat-value"><PnlText value={summary.unrealized_pnl} /></div>
            <div className="stat-sub">{summary.open_positions} open · ₹{summary.open_invested.toLocaleString('en-IN')} invested</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Win Rate</div>
            <div className="stat-value" style={{ color: summary.win_rate > 50 ? 'var(--buy)' : 'var(--sell)' }}>
              {summary.win_rate.toFixed(1)}%
            </div>
          </div>
        </div>
      )}

      {history && <OpenPositions positions={history.open_positions} onExit={exitPosition} />}

      <div className="card-title" style={{ margin: '8px 0 12px' }}>Day-wise History</div>
      {history && history.days.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          No trades yet. Place a Buy or Sell from the Trade tab.
        </div>
      ) : (
        history?.days.map(day => <DayCard key={day.trade_date} day={day} />)
      )}
    </div>
  );
}
