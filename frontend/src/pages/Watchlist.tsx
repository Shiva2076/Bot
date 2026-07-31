import { useEffect, useState, useRef } from 'react';
import { marketAPI, signalsAPI, portfolioAPI } from '../api/client';
import { Zap, RefreshCw, TrendingUp, TrendingDown, Minus, ChevronRight } from 'lucide-react';

const SIGNAL_COLORS = {
  BUY: 'var(--buy)',
  SELL: 'var(--sell)',
  NEUTRAL: 'var(--neutral)',
};

function SignalBadge({ action }: { action: string }) {
  const cls = action === 'BUY' ? 'badge-buy' : action === 'SELL' ? 'badge-sell' : 'badge-neutral';
  const Icon = action === 'BUY' ? TrendingUp : action === 'SELL' ? TrendingDown : Minus;
  return (
    <span className={`signal-badge ${cls}`} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <Icon size={10} /> {action}
    </span>
  );
}

function SignalMiniCard({ signal, stock, onTrade }: { signal: any; stock: any; onTrade: (sym: string, sig: any) => void }) {
  const action = signal?.action || 'NEUTRAL';
  const cardClass = `signal-card ${action.toLowerCase()}`;
  return (
    <div className={cardClass}>
      <div className="signal-header">
        <div>
          <div className="signal-symbol">{stock.symbol.replace('.NS', '')}</div>
          <div className="signal-name">{stock.name}</div>
        </div>
        <SignalBadge action={action} />
      </div>
      <div className="signal-body">
        <div className="signal-prices">
          <div className="price-item">
            <label>Entry</label>
            <div className="value">₹{signal?.entry?.toFixed(2) ?? '--'}</div>
          </div>
          <div className="price-item">
            <label>Stop Loss</label>
            <div className="value stop">₹{signal?.stop_loss?.toFixed(2) ?? '--'}</div>
          </div>
          <div className="price-item">
            <label>Target 1</label>
            <div className="value target">₹{signal?.target_1?.toFixed(2) ?? '--'}</div>
          </div>
        </div>
        <div className="confidence-bar-container">
          <div className="confidence-label">
            <span>Confidence</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
              {signal?.confidence?.toFixed(1) ?? 0}%
            </span>
          </div>
          <div className="confidence-bar-track">
            <div className="confidence-bar-fill" style={{ width: `${signal?.confidence ?? 0}%` }} />
          </div>
        </div>
        {signal?.cautions && signal.cautions.length > 0 && (
          <div className="caution-box">
            <div className="caution-title">
              ⚠️ Consider Waiting
            </div>
            {signal.cautions.slice(0, 2).map((c: string, i: number) => (
              <div key={i} className="caution-item">{c}</div>
            ))}
          </div>
        )}
        {signal?.reasons && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              AI Reasoning
            </div>
            {signal.reasons.slice(0, 3).map((r: string, i: number) => (
              <div key={i} style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', padding: '2px 0', display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--buy)', flexShrink: 0 }}>✔</span> {r}
              </div>
            ))}
          </div>
        )}
        {(action === 'BUY' || action === 'SELL' || action === 'STRONG BUY') && (
          <button 
            className={`btn ${action.includes('BUY') ? 'btn-buy' : 'btn-sell'}`} 
            style={{ width: '100%', marginTop: 12, padding: '8px' }}
            onClick={() => onTrade(stock.symbol, signal)}
          >
            Execute Trade
          </button>
        )}
      </div>
    </div>
  );
}

export default function Watchlist() {
  const [quotes, setQuotes] = useState<any[]>([]);
  const [signals, setSignals] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [loadingSignals, setLoadingSignals] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [view, setView] = useState<'table' | 'cards'>('table');

  const handleTrade = async (symbol: string, signal: any) => {
    try {
      await portfolioAPI.openPosition(symbol, signal);
      alert(`Trade executed for ${symbol}! Check your Portfolio.`);
    } catch (e) {
      console.error(e);
      alert(`Failed to execute trade for ${symbol}.`);
    }
  };

  const fetchQuotes = async () => {
    try {
      const res = await marketAPI.getQuotes();
      setQuotes(res.data.quotes || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchSignals = async () => {
    setLoadingSignals(true);
    try {
      const res = await signalsAPI.getBatch(50);
      setSignals(res.data.signals || {});
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingSignals(false);
    }
  };

  useEffect(() => {
    fetchQuotes();
    fetchSignals();
    const interval = setInterval(fetchQuotes, 60000);
    return () => clearInterval(interval);
  }, []);

  const sectors = ['ALL', ...Array.from(new Set(quotes.map((q: any) => q.sector)))];
  const filtered = filter === 'ALL' ? quotes : quotes.filter((q: any) => q.sector === filter);

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Watchlist</h1>
          <p className="page-subtitle">NIFTY 50 live prices + AI signals</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <select value={view} onChange={e => setView(e.target.value as any)}>
            <option value="table">Table View</option>
            <option value="cards">Signal Cards</option>
          </select>
          <button className="btn btn-ghost" onClick={fetchSignals} disabled={loadingSignals}>
            <Zap size={14} />
            {loadingSignals ? 'Analyzing…' : 'Generate Signals'}
          </button>
          <button className="btn btn-ghost" onClick={fetchQuotes}>
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Sector filter */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 20 }}>
        {sectors.map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`btn ${filter === s ? 'btn-primary' : 'btn-ghost'}`}
            style={{ padding: '5px 12px', fontSize: '0.75rem' }}
          >
            {s}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-screen"><div className="spinner" /><span>Loading quotes…</span></div>
      ) : view === 'table' ? (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Stock</th>
                  <th>Sector</th>
                  <th style={{ textAlign: 'right' }}>Price</th>
                  <th style={{ textAlign: 'right' }}>Change</th>
                  <th style={{ textAlign: 'right' }}>Volume</th>
                  <th style={{ textAlign: 'center' }}>AI Signal</th>
                  <th style={{ textAlign: 'center' }}>Confidence</th>
                  <th style={{ textAlign: 'center' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((q: any) => {
                  const sig = signals[q.symbol];
                  const pos = q.change_pct >= 0;
                  return (
                    <tr key={q.symbol}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{q.symbol?.replace('.NS', '')}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{q.name}</div>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', background: 'var(--bg-elevated)', padding: '2px 8px', borderRadius: 4 }}>
                          {q.sector}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }} className="mono">
                        ₹{q.price?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                      </td>
                      <td style={{ textAlign: 'right' }} className={`mono ${pos ? 'positive' : 'negative'}`}>
                        {pos ? '+' : ''}{q.change_pct?.toFixed(2)}%
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--text-muted)' }} className="mono">
                        {(q.volume / 1e5).toFixed(1)}L
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        {sig ? <SignalBadge action={sig.action} /> : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>–</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        {sig ? (
                          <span className="mono" style={{ fontSize: '0.78rem', color: sig.confidence > 70 ? 'var(--buy)' : sig.confidence > 50 ? 'var(--amber)' : 'var(--sell)' }}>
                            {sig.confidence?.toFixed(1)}%
                          </span>
                        ) : '–'}
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        {sig && (sig.action === 'BUY' || sig.action === 'SELL' || sig.action === 'STRONG BUY') ? (
                          <button 
                            className="btn btn-ghost" 
                            style={{ padding: '4px 10px', fontSize: '0.72rem', border: '1px solid var(--border)' }}
                            onClick={() => handleTrade(q.symbol, sig)}
                          >
                            Trade
                          </button>
                        ) : '–'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="grid-signal">
          {Object.entries(signals).map(([sym, sig]: [string, any]) => {
            const stock = quotes.find(q => q.symbol === sym) || { symbol: sym, name: sym, sector: '' };
            return <SignalMiniCard key={sym} signal={sig} stock={stock} onTrade={handleTrade} />;
          })}
          {Object.keys(signals).length === 0 && (
            <div style={{ color: 'var(--text-muted)', gridColumn: '1/-1', textAlign: 'center', padding: 40 }}>
              Click "Generate Signals" to run the AI agent analysis
            </div>
          )}
        </div>
      )}
    </div>
  );
}
