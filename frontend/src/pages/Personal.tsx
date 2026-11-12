import { useState } from 'react';
import { personalAPI, tradingAPI } from '../api/client';
import { PnlText, Tag } from '../components/TradeBadges';
import { usePolling } from '../hooks/usePolling';
import type { DailyTradeSummary, PersonalHistory, PersonalTrade } from '../types/personal';
import { apiErrorMessage } from '../utils/api-error';

const REFRESH_INTERVAL_MS = 15000;

const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });

const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

const fmt = (v: number | null | undefined, prefix = '₹') =>
  v !== null && v !== undefined ? `${prefix}${v.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '--';

/* ── Trade Detail Drawer ──────────────────────────────────────────────────── */
function TradeDetailDrawer({ trade, onClose }: { trade: PersonalTrade; onClose: () => void }) {
  const pos = trade.pnl >= 0;
  const symbol = trade.symbol.replace('.NS', '');
  const pointsGap = trade.points_gained;

  // Duration
  let duration = '--';
  if (trade.holding_days !== null && trade.holding_days !== undefined) {
    duration = trade.holding_days === 0 ? 'Intraday' : `${trade.holding_days} day${trade.holding_days > 1 ? 's' : ''}`;
  } else if (trade.status === 'OPEN') {
    const ms = Date.now() - new Date(trade.entry_time).getTime();
    const hrs = Math.floor(ms / 3600000);
    const mins = Math.floor((ms % 3600000) / 60000);
    duration = hrs > 0 ? `${hrs}h ${mins}m (live)` : `${mins}m (live)`;
  }

  // Fee extraction from tags
  const entryFees = trade.tags?.entry_fees;
  const exitFees = trade.tags?.exit_fees;

  return (
    <>
      <div className="trade-detail-backdrop" onClick={onClose} />
      <div className="trade-detail-drawer">
        <div className="trade-detail-header">
          <h2>
            <span>{symbol}</span>
            <Tag label={trade.action} color={trade.action === 'BUY' ? 'var(--buy)' : 'var(--sell)'} />
            <Tag label={trade.status === 'OPEN' ? 'OPEN' : 'CLOSED'} color={trade.status === 'OPEN' ? 'var(--amber)' : 'var(--text-muted)'} />
          </h2>
          <button className="trade-detail-close" onClick={onClose}>✕</button>
        </div>

        <div className="trade-detail-body">
          {/* P&L Hero */}
          <div className={`detail-pnl-hero ${pos ? 'profit' : 'loss'}`}>
            <div className="detail-pnl-amount" style={{ color: pos ? 'var(--buy)' : 'var(--sell)' }}>
              {pos ? '+' : '-'}₹{Math.abs(trade.pnl).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </div>
            <div className="detail-pnl-pct" style={{ color: pos ? 'var(--buy)' : 'var(--sell)' }}>
              {pos ? '+' : ''}{trade.pnl_pct.toFixed(2)}%
            </div>
            <div className="detail-pnl-label">
              {trade.status === 'OPEN' ? 'Unrealized P&L' : 'Realized P&L'}
            </div>
          </div>

          {/* Points & Gap */}
          {pointsGap !== null && pointsGap !== undefined && (
            <div className="detail-points-bar">
              <span className="pts-label">Points {pos ? 'Gained' : 'Lost'}</span>
              <span className="pts-value" style={{ color: pos ? 'var(--buy)' : 'var(--sell)' }}>
                {pos ? '+' : ''}{pointsGap.toFixed(2)} pts
              </span>
              <span className="pts-label" style={{ marginLeft: 'auto' }}>Gap</span>
              <span className="pts-value" style={{ color: 'var(--text-primary)' }}>
                {fmt(trade.current_price)} − {fmt(trade.entry_price)}
              </span>
            </div>
          )}

          {/* Entry Details */}
          <div className="detail-section">
            <div className="detail-section-title">Entry Details</div>
            <div className="detail-grid">
              <div className="detail-item">
                <label>Entry Price</label>
                <div className="detail-val">{fmt(trade.entry_price)}</div>
              </div>
              <div className="detail-item">
                <label>Entry Time</label>
                <div className="detail-val">{formatDateTime(trade.entry_time)}</div>
              </div>
              <div className="detail-item">
                <label>Quantity</label>
                <div className="detail-val">{trade.quantity}</div>
              </div>
              <div className="detail-item">
                <label>Invested Amount</label>
                <div className="detail-val">{fmt(trade.invested_amount)}</div>
              </div>
              <div className="detail-item">
                <label>Trade Type</label>
                <div className="detail-val">{trade.trade_type}</div>
              </div>
              <div className="detail-item">
                <label>Order Source</label>
                <div className="detail-val">{trade.order_source.replace(/_/g, ' ')}</div>
              </div>
            </div>
          </div>

          {/* Exit Details */}
          <div className="detail-section">
            <div className="detail-section-title">
              {trade.status === 'OPEN' ? 'Live Status' : 'Exit Details'}
            </div>
            <div className="detail-grid">
              <div className="detail-item">
                <label>{trade.status === 'OPEN' ? 'Current Price (LTP)' : 'Exit Price'}</label>
                <div className="detail-val">{fmt(trade.current_price)}</div>
              </div>
              {trade.exit_time && (
                <div className="detail-item">
                  <label>Exit Time</label>
                  <div className="detail-val">{formatDateTime(trade.exit_time)}</div>
                </div>
              )}
              {trade.exit_reason && (
                <div className="detail-item">
                  <label>Exit Reason</label>
                  <div className="detail-val">{trade.exit_reason}</div>
                </div>
              )}
              <div className="detail-item">
                <label>Duration Held</label>
                <div className="detail-val">{duration}</div>
              </div>
            </div>
          </div>

          {/* Risk Levels */}
          {(trade.stop_loss !== null || trade.target_1 !== null || trade.target_2 !== null) && (
            <div className="detail-section">
              <div className="detail-section-title">Stop Loss & Targets</div>
              <div className="detail-grid">
                <div className="detail-item">
                  <label>Stop Loss</label>
                  <div className={`detail-val ${trade.stop_loss !== null ? 'negative' : 'muted'}`}>
                    {fmt(trade.stop_loss)}
                  </div>
                  {trade.stop_loss !== null && (
                    <div style={{ fontSize: '0.7rem', color: 'var(--sell)', marginTop: 2 }}>
                      {Math.abs(trade.entry_price - trade.stop_loss).toFixed(2)} pts from entry
                    </div>
                  )}
                </div>
                <div className="detail-item">
                  <label>Target 1</label>
                  <div className={`detail-val ${trade.target_1 !== null ? 'positive' : 'muted'}`}>
                    {fmt(trade.target_1)}
                  </div>
                  {trade.target_1 !== null && (
                    <div style={{ fontSize: '0.7rem', color: 'var(--buy)', marginTop: 2 }}>
                      {Math.abs(trade.target_1 - trade.entry_price).toFixed(2)} pts from entry
                    </div>
                  )}
                </div>
                {trade.target_2 !== null && (
                  <div className="detail-item">
                    <label>Target 2</label>
                    <div className="detail-val positive">{fmt(trade.target_2)}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--buy)', marginTop: 2 }}>
                      {Math.abs(trade.target_2 - trade.entry_price).toFixed(2)} pts from entry
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Market Context at Entry */}
          {(trade.confidence_at_entry !== null || trade.market_regime_at_entry) && (
            <div className="detail-section">
              <div className="detail-section-title">Market Context at Entry</div>
              <div className="detail-grid">
                {trade.confidence_at_entry !== null && (
                  <div className="detail-item">
                    <label>Confidence</label>
                    <div className="detail-val">{(trade.confidence_at_entry * 100).toFixed(1)}%</div>
                  </div>
                )}
                {trade.market_regime_at_entry && (
                  <div className="detail-item">
                    <label>Market Regime</label>
                    <div className="detail-val">{trade.market_regime_at_entry}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Fee Breakdown */}
          {(entryFees || exitFees) && (
            <div className="detail-section">
              <div className="detail-section-title">Fee Breakdown</div>
              <div className="detail-grid">
                {entryFees && (
                  <>
                    <div className="detail-item">
                      <label>Entry Fees</label>
                      <div className="detail-val">{fmt(entryFees.total_fees)}</div>
                    </div>
                    <div className="detail-item">
                      <label>Entry Slipped Price</label>
                      <div className="detail-val">{fmt(entryFees.slipped_price)}</div>
                    </div>
                  </>
                )}
                {exitFees && (
                  <>
                    <div className="detail-item">
                      <label>Exit Fees</label>
                      <div className="detail-val">{fmt(exitFees.total_fees)}</div>
                    </div>
                    <div className="detail-item">
                      <label>Exit Slipped Price</label>
                      <div className="detail-val">{fmt(exitFees.slipped_price)}</div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Override Reason */}
          {trade.override_reason && (
            <div className="detail-section">
              <div className="detail-section-title">Override Reason</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {trade.override_reason}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/* ── Open Positions ───────────────────────────────────────────────────────── */
function OpenPositions({
  positions, onExit, onSelect,
}: {
  positions: PersonalTrade[];
  onExit: (id: number) => void;
  onSelect: (t: PersonalTrade) => void;
}) {
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
                <tr key={p.id} className="clickable-row" onClick={() => onSelect(p)}>
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
                      ? <button className="btn btn-sell" style={{ padding: '4px 10px', fontSize: '0.72rem' }} onClick={(e) => { e.stopPropagation(); onExit(p.id); }}>Exit at Market</button>
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

/* ── Day Card ─────────────────────────────────────────────────────────────── */
function DayCard({ day, onSelect }: { day: DailyTradeSummary; onSelect: (t: PersonalTrade) => void }) {
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
              <tr key={t.id} className="clickable-row" onClick={() => onSelect(t)}>
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

/* ── Personal Page ────────────────────────────────────────────────────────── */
export default function Personal() {
  const [history, setHistory] = useState<PersonalHistory | null>(null);
  const [error, setError] = useState('');
  const [selectedTrade, setSelectedTrade] = useState<PersonalTrade | null>(null);

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

  usePolling(fetchHistory, REFRESH_INTERVAL_MS, []);

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

      {history && <OpenPositions positions={history.open_positions} onExit={exitPosition} onSelect={setSelectedTrade} />}

      <div className="card-title" style={{ margin: '8px 0 12px' }}>Day-wise History</div>
      {history && history.days.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          No trades yet. Place a Buy or Sell from the Trade tab.
        </div>
      ) : (
        history?.days.map(day => <DayCard key={day.trade_date} day={day} onSelect={setSelectedTrade} />)
      )}

      {selectedTrade && <TradeDetailDrawer trade={selectedTrade} onClose={() => setSelectedTrade(null)} />}
    </div>
  );
}
