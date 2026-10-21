import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, TrendingUp, Briefcase, Newspaper,
  History, BookOpen, BarChart2, Zap, Activity, User, CandlestickChart
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Watchlist from './pages/Watchlist';
import Portfolio from './pages/Portfolio';
import News from './pages/News';
import TradeHistory from './pages/TradeHistory';
import Journal from './pages/Journal';
import Backtest from './pages/Backtest';
import Personal from './pages/Personal';
import Trade from './pages/Trade';
import { isMarketOpen } from './utils/market-hours';
import './index.css';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/watchlist', icon: TrendingUp, label: 'Watchlist' },
  { to: '/portfolio', icon: Briefcase, label: 'Portfolio' },
  { to: '/news', icon: Newspaper, label: 'News & Sentiment' },
  { to: '/history', icon: History, label: 'Trade History' },
  { to: '/journal', icon: BookOpen, label: 'Learning Journal' },
  { to: '/backtest', icon: BarChart2, label: 'Backtesting' },
  { to: '/trade', icon: CandlestickChart, label: 'Trade' },
  { to: '/personal', icon: User, label: 'Personal' },
];

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <h1>⚡ TradeAI</h1>
        <p>AI Research Platform</p>
      </div>
      <nav className="sidebar-nav">
        <span className="nav-section-label">Research</span>
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="market-status">
          <div className={`status-dot ${isMarketOpen() ? '' : 'closed'}`} />
          <span>NSE {isMarketOpen() ? 'Open' : 'Closed'}</span>
        </div>
        <div style={{ marginTop: 6, color: 'var(--text-muted)' }}>
          Paper Trading Mode 📝
        </div>
      </div>
    </aside>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/news" element={<News />} />
            <Route path="/history" element={<TradeHistory />} />
            <Route path="/journal" element={<Journal />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/trade" element={<Trade />} />
            <Route path="/personal" element={<Personal />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
