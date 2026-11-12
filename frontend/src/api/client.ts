import axios from 'axios';
import type { AutoPaperStatus } from '../types/autoPaper';
import type { OptionChain, OptionExpiries, OptionUnderlying } from '../types/options';
import type { PersonalHistory, PersonalTrade } from '../types/personal';
import type { PremarketReport } from '../types/premarket';
import type { ChartStructureFeatures, OptionPrediction } from '../types/prediction';
import type { TradeDecision } from '../types/tradeDecision';
import type {
  CandleInterval,
  CandleSeries,
  Instrument,
  MarketOrderRequest,
  OpenPositionsResponse,
  PortfolioOpenRequest,
  Tick,
} from '../types/trading';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000,
});

const apiKey = import.meta.env.VITE_APP_API_KEY as string | undefined;
if (apiKey) {
  api.defaults.headers.common['X-API-Key'] = apiKey;
}

// An HTML page means the request never reached the backend (e.g. VITE_API_BASE_URL is unset and
// the dev server or SPA rewrite answered with index.html). Treat it as an error, not as data.
api.interceptors.response.use((response) => {
  const contentType = String(response.headers['content-type'] ?? '');
  if (contentType.includes('text/html')) {
    return Promise.reject(new Error(
      'Backend not reachable: received an HTML page instead of API data. Check VITE_API_BASE_URL.',
    ));
  }
  return response;
});

export const marketAPI = {
  getWatchlist: () => api.get('/api/market/watchlist'),
  getQuotes: () => api.get('/api/market/quotes'),
  getIndices: () => api.get('/api/market/indices'),
  getQuote: (symbol: string) => api.get(`/api/market/quote/${symbol}`),
  getOHLCV: (symbol: string, period = '6mo', interval = '1d') =>
    api.get(`/api/market/ohlcv/${symbol}`, { params: { period, interval } }),
  getBreadth: () => api.get('/api/market/breadth'),
};

export const signalsAPI = {
  getSignal: (symbol: string) => api.get(`/api/signals/generate/${symbol}`),
  getBatch: (limit = 5) => api.get(`/api/signals/batch`, { params: { limit } }),
};

export const portfolioAPI = {
  getSummary: () => api.get('/api/portfolio/summary'),
  getPositions: () => api.get('/api/portfolio/positions'),
  openPosition: (symbol: string, request: PortfolioOpenRequest) =>
    api.post<PersonalTrade>(`/api/portfolio/open/${symbol}`, request),
  closePosition: (symbol: string) => api.post(`/api/portfolio/close/${symbol}`),
};

export const newsAPI = {
  getNews: (symbol?: string) => api.get('/api/news/', { params: symbol ? { symbol } : {} }),
  getCalendar: () => api.get('/api/news/calendar'),
};

export const tradesAPI = {
  getHistory: () => api.get('/api/trades/history'),
  getStats: () => api.get('/api/trades/stats'),
};

export const personalAPI = {
  getHistory: () => api.get<PersonalHistory>('/api/personal/history'),
};

export const tradingAPI = {
  getInstruments: () => api.get<Instrument[]>('/api/trading/instruments'),
  getTick: (symbol: string) => api.get<Tick>('/api/trading/tick', { params: { symbol } }),
  getCandles: (symbol: string, interval: CandleInterval) =>
    api.get<CandleSeries>('/api/trading/candles', { params: { symbol, interval } }),
  getChartStructure: (symbol: string) =>
    api.get<ChartStructureFeatures>('/api/trading/chart-structure', { params: { symbol } }),
  getPositions: () => api.get<OpenPositionsResponse>('/api/trading/positions'),
  getAutoPaper: () => api.get<AutoPaperStatus>('/api/trading/auto-paper'),
  placeOrder: (order: MarketOrderRequest) => api.post<PersonalTrade>('/api/trading/orders', order),
  exitPosition: (tradeId: number) => api.post<PersonalTrade>(`/api/trading/orders/${tradeId}/exit`),
  getDecision: (underlying: OptionUnderlying, expiry: string, force = false) =>
    api.get<TradeDecision>('/api/trading/decision', {
      params: { underlying, expiry, force },
      timeout: 45000,
    }),
};

export const premarketAPI = {
  getLatest: (force = false) =>
    api.get<PremarketReport>('/api/premarket/latest', { params: { force } }),
  getHistory: (limit = 20) =>
    api.get<{ reports: PremarketReport[] }>('/api/premarket/history', { params: { limit } }),
};

export const optionsAPI = {
  getExpiries: (underlying: OptionUnderlying) =>
    api.get<OptionExpiries>('/api/options/expiries', { params: { underlying } }),
  getChain: (underlying: OptionUnderlying, expiry: string) =>
    api.get<OptionChain>('/api/options/chain', { params: { underlying, expiry } }),
  getPrediction: (underlying: OptionUnderlying, expiry: string, force = false) =>
    api.get<OptionPrediction>('/api/options/prediction', {
      params: { underlying, expiry, force },
    }),
};

export const backtestAPI = {
  run: (symbol: string, period: string, strategy: string, capital: number) =>
    api.get('/api/backtest/run', { params: { symbol, period, strategy, capital } }),
  runOrb: (symbol: string, period = '60d', capital = 1000000) =>
    api.get('/api/backtest/orb', { params: { symbol, period, capital } }),
};

export const orbAPI = {
  evaluate: (symbol: string) => api.post('/api/orb/evaluate', { symbol }),
  execute: (symbol: string) => api.post('/api/orb/execute', { symbol }),
};

export const sectorsAPI = {
  getSectors: () => api.get('/api/sectors/'),
  getRecommendation: () => api.get('/api/sectors/recommendation'),
};

export default api;
