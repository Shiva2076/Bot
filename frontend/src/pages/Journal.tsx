import { useEffect, useState } from 'react';
import { tradesAPI } from '../api/client';
import { BookOpen } from 'lucide-react';

export default function Journal() {
  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    tradesAPI.getHistory().then(res => {
      setTrades((res.data.trades || []).filter((t: any) => t.status === 'CLOSED'));
    }).finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Learning Journal</h1>
        <p className="page-subtitle">Detailed analysis of every paper trade — what worked and what failed</p>
      </div>

      {loading ? (
        <div className="loading-screen"><div className="spinner" /></div>
      ) : trades.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 60 }}>
          <BookOpen size={40} style={{ color: 'var(--text-muted)', marginBottom: 16 }} />
          <div style={{ fontWeight: 600, fontSize: '1.1rem', marginBottom: 8 }}>Journal is Empty</div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Complete paper trades to build your learning dataset.
            Each closed trade is automatically logged here with AI reasoning.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[...trades].reverse().map((trade: any, i: number) => {
            const win = trade.outcome === 'WIN';
            return (
              <div key={i} className="card" style={{ borderLeft: `3px solid ${win ? 'var(--buy)' : 'var(--sell)'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: '1.1rem', fontWeight: 700 }}>{trade.symbol?.replace('.NS', '')}</span>
                      <span style={{
                        padding: '2px 8px', borderRadius: 12, fontSize: '0.65rem', fontWeight: 700,
                        background: win ? 'var(--buy-glow)' : 'var(--sell-glow)',
                        color: win ? 'var(--buy)' : 'var(--sell)',
                      }}>
                        {trade.outcome || 'CLOSED'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                      {trade.exit_time ? new Date(trade.exit_time).toLocaleDateString('en-IN', { dateStyle: 'medium' }) : '--'}
                      {trade.market_regime_at_entry && ` · ${trade.market_regime_at_entry}`}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '1.2rem', color: win ? 'var(--buy)' : 'var(--sell)' }}>
                      {(trade.pnl || 0) >= 0 ? '+' : ''}₹{Math.abs(trade.pnl || 0).toFixed(2)}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: win ? 'var(--buy)' : 'var(--sell)' }}>
                      {(trade.pnl_pct || 0) >= 0 ? '+' : ''}{trade.pnl_pct?.toFixed(2)}%
                    </div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 14 }}>
                  {[
                    { l: 'Entry', v: `₹${trade.entry_price?.toFixed(2)}` },
                    { l: 'Exit', v: `₹${trade.exit_price?.toFixed(2)}` },
                    { l: 'Qty', v: trade.quantity },
                    { l: 'Exit Reason', v: trade.exit_reason || '--' },
                  ].map(item => (
                    <div key={item.l}>
                      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{item.l}</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, marginTop: 2 }}>{item.v}</div>
                    </div>
                  ))}
                </div>

                {trade.confidence_at_entry && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 5 }}>
                      <span>AI Confidence at Entry</span>
                      <span className="mono">{trade.confidence_at_entry?.toFixed(1)}%</span>
                    </div>
                    <div className="confidence-bar-track">
                      <div className="confidence-bar-fill" style={{ width: `${trade.confidence_at_entry}%` }} />
                    </div>
                  </div>
                )}

                <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', padding: '10px 14px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                    📝 Lesson
                  </div>
                  {win
                    ? <span style={{ color: 'var(--buy)' }}>✔ Strategy worked as expected. Confidence was {trade.confidence_at_entry >= 70 ? 'high (> 70%)' : 'moderate'} at entry.</span>
                    : <span style={{ color: 'var(--sell)' }}>✗ Trade hit {trade.exit_reason}. Review entry conditions and tighten filters if {trade.confidence_at_entry < 65 ? 'confidence is below 65%' : 'market regime is unfavorable'}.</span>
                  }
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
