import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 30000,
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
  openPosition: (symbol: string, signal: object) =>
    api.post(`/api/portfolio/open/${symbol}`, signal),
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

export const backtestAPI = {
  run: (symbol: string, period: string, strategy: string, capital: number) =>
    api.get('/api/backtest/run', { params: { symbol, period, strategy, capital } }),
};

export const sectorsAPI = {
  getSectors: () => api.get('/api/sectors/'),
  getRecommendation: () => api.get('/api/sectors/recommendation'),
};

export default api;
