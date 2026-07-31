import { useEffect, useState } from 'react';
import { newsAPI } from '../api/client';
import { Calendar, RefreshCw, ExternalLink } from 'lucide-react';

function SentimentBar({ compound }: { compound: number }) {
  const pct = ((compound + 1) / 2 * 100).toFixed(0);
  const color = compound > 0.05 ? 'var(--buy)' : compound < -0.05 ? 'var(--sell)' : 'var(--neutral)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: '0.65rem', fontFamily: 'var(--font-mono)', color }}>{compound.toFixed(2)}</span>
    </div>
  );
}

export default function News() {
  const [news, setNews] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL'>('ALL');

  const fetchData = async () => {
    try {
      const [newsRes, calRes] = await Promise.allSettled([newsAPI.getNews(), newsAPI.getCalendar()]);
      if (newsRes.status === 'fulfilled') setNews(newsRes.value.data.news || []);
      if (calRes.status === 'fulfilled') setEvents(calRes.value.data.events || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const filtered = filter === 'ALL' ? news : news.filter((n: any) => n.label === filter);

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">News & Sentiment</h1>
          <p className="page-subtitle">AI-scored financial news from Indian markets</p>
        </div>
        <button className="btn btn-ghost" onClick={fetchData}><RefreshCw size={14} /> Refresh</button>
      </div>

      <div className="grid-2" style={{ gap: 20 }}>
        {/* News Feed */}
        <div style={{ gridColumn: '1 / 2' }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {['ALL', 'POSITIVE', 'NEGATIVE', 'NEUTRAL'].map(f => (
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
            <div className="card">
              {filtered.slice(0, 30).map((item: any, i: number) => (
                <div key={i} className="news-item">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div className="news-source">{item.source}</div>
                      <div className="news-title">
                        <a href={item.link} target="_blank" rel="noopener noreferrer">{item.title}</a>
                      </div>
                      {item.summary && (
                        <div style={{ fontSize: '0.73rem', color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.5 }}>
                          {item.summary.slice(0, 120)}…
                        </div>
                      )}
                      <div className="news-meta">
                        <span className={`sentiment-tag ${(item.label || 'NEUTRAL').toLowerCase()}`}>{item.label || 'NEUTRAL'}</span>
                        {item.related_symbols?.slice(0, 3).map((s: string) => (
                          <span key={s} style={{ fontSize: '0.65rem', color: 'var(--accent)', background: 'rgba(59,130,246,0.08)', padding: '1px 6px', borderRadius: 4 }}>
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <a href={item.link} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-muted)', flexShrink: 0, marginTop: 4 }}>
                      <ExternalLink size={12} />
                    </a>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <SentimentBar compound={item.compound_score || 0} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Economic Calendar */}
        <div>
          <div style={{ marginBottom: 16 }}>
            <div className="card-title" style={{ marginBottom: 12 }}>📅 Economic Calendar</div>
          </div>
          <div className="card" style={{ padding: 0 }}>
            {events.slice(0, 12).map((event: any, i: number) => (
              <div key={i} style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div style={{
                  padding: '3px 8px',
                  borderRadius: 4,
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  flexShrink: 0,
                  background: event.impact === 'HIGH' ? 'var(--sell-glow)' : event.impact === 'MEDIUM' ? 'rgba(245,158,11,0.1)' : 'var(--bg-elevated)',
                  color: event.impact === 'HIGH' ? 'var(--sell)' : event.impact === 'MEDIUM' ? 'var(--amber)' : 'var(--text-muted)',
                  border: `1px solid ${event.impact === 'HIGH' ? 'rgba(244,63,94,0.2)' : event.impact === 'MEDIUM' ? 'rgba(245,158,11,0.2)' : 'var(--border)'}`,
                }}>
                  {event.impact}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.82rem' }}>{event.name}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>
                    {event.date} · {event.category}
                  </div>
                  {event.warning && (
                    <div style={{ fontSize: '0.7rem', color: 'var(--amber)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                      ⚠️ Within 48 hours
                    </div>
                  )}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                  {event.days_away}d
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
