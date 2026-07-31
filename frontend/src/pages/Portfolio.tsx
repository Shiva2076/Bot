import { useEffect, useState } from 'react';
import { portfolioAPI, tradesAPI } from '../api/client';
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react';

function PnlBadge({ pnl }: { pnl: number }) {
  const pos = pnl >= 0;
  return (
    <span style={{ color: pos ? 'var(--buy)' : 'var(--sell)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
      {pos ? '+' : ''}₹{Math.abs(pnl).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
    </span>
  );
}

export default function Portfolio() {
  const [portfolio, setPortfolio] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [portRes, statsRes] = await Promise.allSettled([
        portfolioAPI.getSummary(),
        tradesAPI.getStats(),
      ]);
      if (portRes.status === 'fulfilled') {
        setPortfolio(portRes.value.data.portfolio);
        setPositions(portRes.value.data.positions || []);
      }
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
    } finally {
      setLoading(false);
    }
  };

  const closePosition = async (symbol: string) => {
    await portfolioAPI.closePosition(symbol);
    fetchData();
  };

  useEffect(() => { fetchData(); }, []);

  if (loading) return <div className="loading-screen"><div className="spinner" /></div>;

  const capital = portfolio?.starting_capital || 1000000;
  const totalValue = portfolio?.total_value || capital;
  const totalPnl = portfolio?.total_pnl || 0;
  const totalPnlPct = portfolio?.total_pnl_pct || 0;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Paper Portfolio</h1>
        <p className="page-subtitle">Virtual trading performance · Starting capital ₹{(capital / 100000).toFixed(0)}L</p>
      </div>

      {/* Stats row */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-label">Portfolio Value</div>
          <div className="stat-value" style={{ color: totalPnl >= 0 ? 'var(--buy)' : 'var(--sell)' }}>
            ₹{(totalValue / 100000).toFixed(2)}L
          </div>
          <div className="stat-sub" style={{ color: totalPnlPct >= 0 ? 'var(--buy)' : 'var(--sell)' }}>
            {totalPnlPct >= 0 ? '+' : ''}{totalPnlPct?.toFixed(2)}% total return
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Available Cash</div>
          <div className="stat-value mono">₹{((portfolio?.cash || 0) / 100000).toFixed(2)}L</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Win Rate</div>
          <div className="stat-value" style={{ color: (stats?.win_rate || 0) > 50 ? 'var(--buy)' : 'var(--sell)' }}>
            {stats?.win_rate?.toFixed(1) ?? '--'}%
          </div>
          <div className="stat-sub">{stats?.total_trades ?? 0} total trades</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total P&L</div>
          <div className="stat-value"><PnlBadge pnl={totalPnl} /></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Open Positions</div>
          <div className="stat-value">{positions.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg Win</div>
          <div className="stat-value positive">+{stats?.avg_win_pct?.toFixed(2) ?? '--'}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg Loss</div>
          <div className="stat-value negative">{stats?.avg_loss_pct?.toFixed(2) ?? '--'}%</div>
        </div>
      </div>

      {/* Open Positions */}
      <div className="card" style={{ marginBottom: 20, padding: 0 }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <span className="card-title">Open Positions ({positions.length})</span>
        </div>
        {positions.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            No open positions. Go to Watchlist and generate signals to trade.
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th style={{ textAlign: 'right' }}>Entry</th>
                  <th style={{ textAlign: 'right' }}>Current</th>
                  <th style={{ textAlign: 'right' }}>Qty</th>
                  <th style={{ textAlign: 'right' }}>Invested</th>
                  <th style={{ textAlign: 'right' }}>Unrealized P&L</th>
                  <th style={{ textAlign: 'right' }}>SL / Target</th>
                  <th style={{ textAlign: 'center' }}>Confidence</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos: any) => {
                  const pnl = pos.unrealized_pnl || 0;
                  const pnlPct = pos.unrealized_pnl_pct || 0;
                  return (
                    <tr key={pos.symbol}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{pos.symbol?.replace('.NS', '')}</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          {pos.market_regime || 'Paper Trade'}
                        </div>
                      </td>
                      <td style={{ textAlign: 'right' }} className="mono">₹{pos.entry_price?.toFixed(2)}</td>
                      <td style={{ textAlign: 'right' }} className={`mono ${pnl >= 0 ? 'positive' : 'negative'}`}>
                        ₹{pos.current_price?.toFixed(2)}
                      </td>
                      <td style={{ textAlign: 'right' }} className="mono">{pos.quantity}</td>
                      <td style={{ textAlign: 'right' }} className="mono">
                        ₹{(pos.invested / 1000).toFixed(1)}K
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div className={`mono ${pnl >= 0 ? 'positive' : 'negative'}`} style={{ fontWeight: 700 }}>
                          {pnl >= 0 ? '+' : ''}₹{Math.abs(pnl).toFixed(2)}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: pnlPct >= 0 ? 'var(--buy)' : 'var(--sell)' }}>
                          ({pnlPct >= 0 ? '+' : ''}{pnlPct?.toFixed(2)}%)
                        </div>
                      </td>
                      <td style={{ textAlign: 'right', fontSize: '0.75rem' }}>
                        <div style={{ color: 'var(--sell)' }}>SL: ₹{pos.stop_loss?.toFixed(2) ?? '--'}</div>
                        <div style={{ color: 'var(--buy)' }}>T1: ₹{pos.target_1?.toFixed(2) ?? '--'}</div>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <span className="mono" style={{ fontSize: '0.78rem', color: (pos.confidence || 0) > 70 ? 'var(--buy)' : 'var(--amber)' }}>
                          {pos.confidence?.toFixed(0) ?? '--'}%
                        </span>
                      </td>
                      <td>
                        <button className="btn btn-sell" style={{ padding: '4px 10px', fontSize: '0.72rem' }} onClick={() => closePosition(pos.symbol)}>
                          Close
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
