import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Activity, Zap, RefreshCw } from 'lucide-react';
import { marketAPI, sectorsAPI, newsAPI } from '../api/client';

function IndexCard({ index }: { index: any }) {
  const pos = index.change_pct >= 0;
  return (
    <div className="index-card">
      <div className="index-name">{index.name || index.symbol}</div>
      <div className={`index-price ${pos ? 'positive' : 'negative'}`}>
        ₹{index.price?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
      </div>
      <div className={`index-change ${pos ? 'positive' : 'negative'}`}>
        {pos ? '▲' : '▼'} {Math.abs(index.change_pct).toFixed(2)}%
        <span style={{ color: 'var(--text-muted)', marginLeft: 6, fontWeight: 400 }}>
          ({pos ? '+' : ''}{index.change?.toFixed(2)})
        </span>
      </div>
    </div>
  );
}

function SectorHeatmap({ sectors }: { sectors: any[] }) {
  return (
    <div className="sector-grid">
      {sectors.map((s) => (
        <div key={s.key} className={`sector-tile ${s.status === 'LEADING' ? 'leading' : s.status === 'LAGGING' ? 'lagging' : 'neutral-sector'}`}>
          <div className="sector-name">{s.name}</div>
          <div className="sector-pct">
            {s.change_pct >= 0 ? '+' : ''}{s.change_pct?.toFixed(2)}%
          </div>
          <div className="sector-rank">#{s.rank}</div>
        </div>
      ))}
    </div>
  );
}

function RegimeBadge({ regime }: { regime: any }) {
  if (!regime) return null;
  return (
    <div className={`regime-badge ${regime.color || 'gray'}`}>
      <Activity size={14} />
      <span>{regime.label || regime.regime}</span>
    </div>
  );
}

function BreadthCard({ breadth }: { breadth: any }) {
  const total = breadth?.total || 50;
  const advPct = ((breadth?.advancing || 0) / total * 100).toFixed(0);
  const decPct = ((breadth?.declining || 0) / total * 100).toFixed(0);
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Market Breadth</span>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>NIFTY 50</span>
      </div>
      <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
        <div style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--buy)' }}>{breadth?.advancing ?? '--'}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Advancing</div>
        </div>
        <div style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--neutral)' }}>{breadth?.unchanged ?? '--'}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Unchanged</div>
        </div>
        <div style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--sell)' }}>{breadth?.declining ?? '--'}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Declining</div>
        </div>
      </div>
      <div style={{ height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'hidden', display: 'flex' }}>
        <div style={{ width: `${advPct}%`, background: 'var(--buy)', transition: 'width 0.8s ease' }} />
        <div style={{ width: `${decPct}%`, background: 'var(--sell)', transition: 'width 0.8s ease' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: '0.7rem', color: 'var(--text-muted)' }}>
        <span>A/D Ratio: {breadth?.advance_decline_ratio?.toFixed(2) ?? '--'}</span>
        <span>{total} stocks tracked</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [indices, setIndices] = useState<any[]>([]);
  const [sectors, setSectors] = useState<any[]>([]);
  const [breadth, setBreadth] = useState<any>(null);
  const [regime, setRegime] = useState<any>(null);
  const [news, setNews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      const [indRes, secRes, breadthRes, newsRes] = await Promise.allSettled([
        marketAPI.getIndices(),
        sectorsAPI.getSectors(),
        marketAPI.getBreadth(),
        newsAPI.getNews(),
      ]);
      if (indRes.status === 'fulfilled') setIndices(indRes.value.data.indices || []);
      if (secRes.status === 'fulfilled') setSectors(secRes.value.data.sectors || []);
      if (breadthRes.status === 'fulfilled') setBreadth(breadthRes.value.data);
      if (newsRes.status === 'fulfilled') setNews(newsRes.value.data.news?.slice(0, 6) || []);
      setLastUpdated(new Date());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000); // refresh every minute
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 className="page-title">Market Dashboard</h1>
          <p className="page-subtitle">
            Live NSE/BSE overview · Updated {lastUpdated.toLocaleTimeString('en-IN')}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {regime && <RegimeBadge regime={regime} />}
          <button className="btn btn-ghost" onClick={fetchData}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading-screen">
          <div className="spinner" />
          <span>Fetching live market data...</span>
        </div>
      ) : (
        <>
          {/* Index Bar */}
          <div className="index-bar">
            {indices.length > 0
              ? indices.map((idx: any) => <IndexCard key={idx.symbol} index={idx} />)
              : [{ symbol: '^NSEI', name: 'NIFTY 50', price: null, change_pct: 0, change: 0 }].map(idx => (
                  <div key={idx.symbol} className="index-card">
                    <div className="index-name">{idx.name}</div>
                    <div className="index-price" style={{ color: 'var(--text-muted)' }}>Loading…</div>
                  </div>
                ))}
          </div>

          {/* Main grid */}
          <div className="grid-2" style={{ gap: 20 }}>
            {/* Sector Heatmap */}
            <div className="card" style={{ gridColumn: '1 / -1' }}>
              <div className="card-header">
                <span className="card-title">🔥 Sector Performance Today</span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Leading vs Lagging
                </span>
              </div>
              {sectors.length > 0
                ? <SectorHeatmap sectors={sectors} />
                : <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Fetching sector data…</div>}
            </div>

            {/* Breadth */}
            {breadth && <BreadthCard breadth={breadth} />}

            {/* News */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">📰 Latest News</span>
              </div>
              {news.length > 0 ? news.map((item: any, i: number) => (
                <div key={i} className="news-item">
                  <div className="news-source">{item.source}</div>
                  <div className="news-title">
                    <a href={item.link} target="_blank" rel="noopener noreferrer">{item.title}</a>
                  </div>
                  <div className="news-meta">
                    <span className={`sentiment-tag ${item.label?.toLowerCase() || 'neutral'}`}>
                      {item.label || 'NEUTRAL'}
                    </span>
                  </div>
                </div>
              )) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading news…</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
