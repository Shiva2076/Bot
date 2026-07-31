import { useEffect, useState } from 'react';
import { tradesAPI } from '../api/client';

export default function TradeHistory() {
  const [trades, setTrades] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'WIN' | 'LOSS'>('ALL');

  useEffect(() => {
    Promise.allSettled([tradesAPI.getHistory(), tradesAPI.getStats()]).then(([histRes, statsRes]) => {
      if (histRes.status === 'fulfilled') setTrades(histRes.value.data.trades || []);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
    }).finally(() => setLoading(false));
  }, []);

  const filtered = filter === 'ALL' ? trades : trades.filter(t => t.outcome === filter);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Trade History</h1>
        <p className="page-subtitle">All closed paper trades with P&L analysis</p>
      </div>

      {stats && (
        <div className="stats-row" style={{ marginBottom: 20 }}>
          {[
            { label: 'Total Trades', value: stats.total_trades },
            { label: 'Win Rate', value: `${stats.win_rate?.toFixed(1)}%`, color: (stats.win_rate || 0) > 50 ? 'var(--buy)' : 'var(--sell)' },
            { label: 'Wins', value: stats.winning_trades, color: 'var(--buy)' },
            { label: 'Losses', value: stats.losing_trades, color: 'var(--sell)' },
            { label: 'Avg Win', value: `+${stats.avg_win_pct?.toFixed(2)}%`, color: 'var(--buy)' },
            { label: 'Avg Loss', value: `${stats.avg_loss_pct?.toFixed(2)}%`, color: 'var(--sell)' },
          ].map(s => (
            <div key={s.label} className="stat-card">
              <div className="stat-label">{s.label}</div>
              <div className="stat-value mono" style={{ color: s.color }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['ALL', 'WIN', 'LOSS'].map(f => (
          <button key={f} onClick={() => setFilter(f as any)}
            className={`btn ${filter === f ? 'btn-primary' : 'btn-ghost'}`}
            style={{ padding: '5px 12px', fontSize: '0.72rem' }}>
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-screen"><div className="spinner" /></div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          {filtered.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
              No trades yet. Open positions from the Watchlist to start paper trading.
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Stock</th>
                    <th style={{ textAlign: 'right' }}>Entry</th>
                    <th style={{ textAlign: 'right' }}>Exit</th>
                    <th style={{ textAlign: 'right' }}>Qty</th>
                    <th style={{ textAlign: 'right' }}>P&L</th>
                    <th style={{ textAlign: 'right' }}>Return</th>
                    <th style={{ textAlign: 'center' }}>Outcome</th>
                    <th>Exit Reason</th>
                    <th style={{ textAlign: 'center' }}>Confidence</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {[...filtered].reverse().map((t: any, i: number) => {
                    const win = t.outcome === 'WIN';
                    return (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{t.symbol?.replace('.NS', '')}</td>
                        <td style={{ textAlign: 'right' }} className="mono">₹{t.entry_price?.toFixed(2)}</td>
                        <td style={{ textAlign: 'right' }} className="mono">₹{t.exit_price?.toFixed(2)}</td>
                        <td style={{ textAlign: 'right' }} className="mono">{t.quantity}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 700, color: win ? 'var(--buy)' : 'var(--sell)' }}>
                          {t.pnl >= 0 ? '+' : ''}₹{Math.abs(t.pnl).toFixed(2)}
                        </td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: win ? 'var(--buy)' : 'var(--sell)' }}>
                          {(t.pnl_pct || 0) >= 0 ? '+' : ''}{t.pnl_pct?.toFixed(2)}%
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <span style={{
                            padding: '2px 8px', borderRadius: 12, fontSize: '0.65rem', fontWeight: 700,
                            background: win ? 'var(--buy-glow)' : 'var(--sell-glow)',
                            color: win ? 'var(--buy)' : 'var(--sell)',
                          }}>
                            {t.outcome}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{t.exit_reason}</td>
                        <td style={{ textAlign: 'center' }} className="mono">
                          <span style={{ fontSize: '0.75rem', color: (t.confidence_at_entry || 0) > 70 ? 'var(--buy)' : 'var(--amber)' }}>
                            {t.confidence_at_entry?.toFixed(0) ?? '--'}%
                          </span>
                        </td>
                        <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {t.exit_time ? new Date(t.exit_time).toLocaleDateString('en-IN') : '--'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
