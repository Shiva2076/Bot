import { useState } from 'react';
import { backtestAPI } from '../api/client';
import { Play, BarChart2, TrendingUp, TrendingDown } from 'lucide-react';

const STRATEGIES = [
  { value: 'rsi_macd', label: 'RSI + MACD Crossover', desc: 'Buy when RSI < 35 and MACD crosses up' },
  { value: 'ema_crossover', label: 'EMA Crossover (20/50)', desc: 'Buy when EMA20 crosses above EMA50' },
  { value: 'ema_trend', label: 'Trend Following (200 EMA + RSI)', desc: 'Buy above 200 EMA with RSI pullback' },
];

const NIFTY50 = [
  'TCS.NS', 'INFY.NS', 'RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS',
  'SBIN.NS', 'WIPRO.NS', 'AXISBANK.NS', 'TATAMOTORS.NS', 'BAJFINANCE.NS',
  'SUNPHARMA.NS', 'MARUTI.NS', 'TITAN.NS', 'KOTAKBANK.NS', 'LT.NS',
  '^NSEI', '^NSEBANK',
];

function MetricCard({ label, value, sub, color }: any) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value mono" style={{ color }}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function EquityCurve({ data }: { data: number[] }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const W = 800, H = 150;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * H;
    return `${x},${y}`;
  }).join(' ');
  const lastVal = data[data.length - 1];
  const firstVal = data[0];
  const color = lastVal >= firstVal ? '#10b981' : '#f43f5e';
  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="card-header"><span className="card-title">📈 Equity Curve</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 150 }}>
        <defs>
          <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2" />
        <polygon points={`0,${H} ${pts} ${W},${H}`} fill="url(#eq-grad)" />
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 8 }}>
        <span>Start: ₹{firstVal.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
        <span style={{ color }}>{data.length} candles</span>
        <span>End: ₹{lastVal.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
      </div>
    </div>
  );
}

export default function Backtest() {
  const [symbol, setSymbol] = useState('TCS.NS');
  const [period, setPeriod] = useState('5y');
  const [strategy, setStrategy] = useState('rsi_macd');
  const [capital, setCapital] = useState(1000000);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const runBacktest = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await backtestAPI.run(symbol, period, strategy, capital);
      setResult(res.data);
    } catch (e: any) {
      setError(e.message || 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Backtesting Engine</h1>
        <p className="page-subtitle">Test trading strategies on historical NSE data (2018–present)</p>
      </div>

      {/* Config */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header"><span className="card-title">Strategy Configuration</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 20 }}>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>Symbol</label>
            <select value={symbol} onChange={e => setSymbol(e.target.value)} style={{ width: '100%' }}>
              {NIFTY50.map(s => <option key={s} value={s}>{s.replace('.NS', '')}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>Period</label>
            <select value={period} onChange={e => setPeriod(e.target.value)} style={{ width: '100%' }}>
              <option value="1y">1 Year</option>
              <option value="2y">2 Years</option>
              <option value="5y">5 Years</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>Starting Capital</label>
            <select value={capital} onChange={e => setCapital(Number(e.target.value))} style={{ width: '100%' }}>
              <option value={500000}>₹5 Lakh</option>
              <option value={1000000}>₹10 Lakh</option>
              <option value={2000000}>₹20 Lakh</option>
            </select>
          </div>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: 8 }}>Strategy</label>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {STRATEGIES.map(s => (
              <div
                key={s.value}
                onClick={() => setStrategy(s.value)}
                style={{
                  padding: '10px 14px', borderRadius: 'var(--radius-md)', cursor: 'pointer', flex: 1, minWidth: 200,
                  background: strategy === s.value ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                  border: `1px solid ${strategy === s.value ? 'rgba(59,130,246,0.4)' : 'var(--border)'}`,
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '0.83rem', color: strategy === s.value ? 'var(--accent)' : 'var(--text-primary)' }}>
                  {s.label}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>{s.desc}</div>
              </div>
            ))}
          </div>
        </div>

        <button className="btn btn-primary" onClick={runBacktest} disabled={loading}>
          <Play size={14} /> {loading ? 'Running…' : 'Run Backtest'}
        </button>
        {error && <div style={{ color: 'var(--sell)', marginTop: 10, fontSize: '0.82rem' }}>⚠️ {error}</div>}
      </div>

      {/* Results */}
      {result && !result.error && (
        <>
          <div style={{ marginBottom: 16 }}>
            <span className="card-title">Results: {result.symbol?.replace('.NS', '')} · {result.strategy} · {result.period}</span>
          </div>
          <div className="stats-row" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
            <MetricCard label="Win Rate" value={`${result.win_rate}%`} color={(result.win_rate || 0) > 50 ? 'var(--buy)' : 'var(--sell)'} />
            <MetricCard label="CAGR" value={`${result.cagr_pct}%`} color={(result.cagr_pct || 0) > 0 ? 'var(--buy)' : 'var(--sell)'} />
            <MetricCard label="Sharpe Ratio" value={result.sharpe_ratio} color={(result.sharpe_ratio || 0) > 1 ? 'var(--buy)' : 'var(--amber)'} />
            <MetricCard label="Max Drawdown" value={`${result.max_drawdown_pct}%`} color="var(--sell)" />
            <MetricCard label="Profit Factor" value={result.profit_factor === Infinity ? '∞' : result.profit_factor} color={(result.profit_factor || 0) > 1 ? 'var(--buy)' : 'var(--sell)'} />
            <MetricCard label="Total Return" value={`${(result.total_return_pct || 0) >= 0 ? '+' : ''}${result.total_return_pct}%`} color={(result.total_return_pct || 0) > 0 ? 'var(--buy)' : 'var(--sell)'} />
            <MetricCard label="Total Trades" value={result.total_trades} />
            <MetricCard label="Avg Holding" value={`${result.avg_holding_days}d`} />
            <MetricCard label="Final Capital" value={`₹${((result.final_capital || 0) / 100000).toFixed(1)}L`} color={(result.net_pnl || 0) > 0 ? 'var(--buy)' : 'var(--sell)'} />
          </div>
          <EquityCurve data={result.equity_curve || []} />
        </>
      )}
      {result?.error && (
        <div className="card" style={{ color: 'var(--sell)' }}>⚠️ {result.error}</div>
      )}
    </div>
  );
}
