"""
Market Data Service — fetches live and historical NSE/BSE data via yfinance.
NSE stocks use the .NS suffix (e.g., TCS.NS, RELIANCE.NS)
Indices: ^NSEI (NIFTY50), ^NSEBANK (BANKNIFTY), ^BSESN (SENSEX)
Note: yfinance provides 15-min delayed data for free.
(Updated to use in-memory Python dictionaries for caching)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yfinance as yf
import pandas as pd
import json
import pytz
import time
from config import settings

IST = pytz.timezone("Asia/Kolkata")

# ── Watchlist ──────────────────────────────────────────────────────────────────
NIFTY50_STOCKS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "sector": "Banking"},
    {"symbol": "INFY.NS", "name": "Infosys", "sector": "IT"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "sector": "Banking"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"symbol": "ITC.NS", "name": "ITC", "sector": "FMCG"},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "sector": "Banking"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel", "sector": "Telecom"},
    {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "sector": "Banking"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro", "sector": "Infra"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank", "sector": "Banking"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance", "sector": "Finance"},
    {"symbol": "WIPRO.NS", "name": "Wipro", "sector": "IT"},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki", "sector": "Auto"},
    {"symbol": "HCLTECH.NS", "name": "HCL Technologies", "sector": "IT"},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharmaceutical", "sector": "Pharma"},
    {"symbol": "ULTRACEMCO.NS", "name": "UltraTech Cement", "sector": "Cement"},
    {"symbol": "TITAN.NS", "name": "Titan Company", "sector": "Consumer"},
    {"symbol": "NESTLEIND.NS", "name": "Nestle India", "sector": "FMCG"},
    {"symbol": "TECHM.NS", "name": "Tech Mahindra", "sector": "IT"},
    {"symbol": "M&M.NS", "name": "Mahindra & Mahindra", "sector": "Auto"},
    {"symbol": "ASIANPAINT.NS", "name": "Asian Paints", "sector": "Consumer"},
    {"symbol": "POWERGRID.NS", "name": "Power Grid Corp", "sector": "Energy"},
    {"symbol": "NTPC.NS", "name": "NTPC", "sector": "Energy"},
    {"symbol": "ONGC.NS", "name": "ONGC", "sector": "Energy"},
    {"symbol": "JSWSTEEL.NS", "name": "JSW Steel", "sector": "Metal"},
    {"symbol": "TATASTEEL.NS", "name": "Tata Steel", "sector": "Metal"},
    {"symbol": "HINDALCO.NS", "name": "Hindalco Industries", "sector": "Metal"},
    {"symbol": "ADANIENT.NS", "name": "Adani Enterprises", "sector": "Conglomerate"},
    {"symbol": "ADANIPORTS.NS", "name": "Adani Ports", "sector": "Infra"},
    {"symbol": "CIPLA.NS", "name": "Cipla", "sector": "Pharma"},
    {"symbol": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories", "sector": "Pharma"},
    {"symbol": "DIVISLAB.NS", "name": "Divi's Laboratories", "sector": "Pharma"},
    {"symbol": "EICHERMOT.NS", "name": "Eicher Motors", "sector": "Auto"},
    {"symbol": "BAJAJ-AUTO.NS", "name": "Bajaj Auto", "sector": "Auto"},
    {"symbol": "HEROMOTOCO.NS", "name": "Hero MotoCorp", "sector": "Auto"},
    {"symbol": "GRASIM.NS", "name": "Grasim Industries", "sector": "Cement"},
    {"symbol": "INDUSINDBK.NS", "name": "IndusInd Bank", "sector": "Banking"},
    {"symbol": "BPCL.NS", "name": "BPCL", "sector": "Energy"},
    {"symbol": "COALINDIA.NS", "name": "Coal India", "sector": "Energy"},
    {"symbol": "UPL.NS", "name": "UPL", "sector": "Chemical"},
    {"symbol": "SBILIFE.NS", "name": "SBI Life Insurance", "sector": "Finance"},
    {"symbol": "HDFCLIFE.NS", "name": "HDFC Life Insurance", "sector": "Finance"},
    {"symbol": "BAJAJFINSV.NS", "name": "Bajaj Finserv", "sector": "Finance"},
    {"symbol": "APOLLOHOSP.NS", "name": "Apollo Hospitals", "sector": "Healthcare"},
    {"symbol": "BRITANNIA.NS", "name": "Britannia Industries", "sector": "FMCG"},
    {"symbol": "TATACONSUM.NS", "name": "Tata Consumer Products", "sector": "FMCG"},
]

INDICES = [
    {"symbol": "^NSEI", "name": "NIFTY 50"},
    {"symbol": "^NSEBANK", "name": "BANK NIFTY"},
    {"symbol": "^BSESN", "name": "SENSEX"},
    {"symbol": "^CNXIT", "name": "NIFTY IT"},
    {"symbol": "^CNXAUTO", "name": "NIFTY AUTO"},
    {"symbol": "^CNXPHARMA", "name": "NIFTY PHARMA"},
    {"symbol": "^CNXFMCG", "name": "NIFTY FMCG"},
    {"symbol": "^CNXMETAL", "name": "NIFTY METAL"},
    {"symbol": "^CNXREALTY", "name": "NIFTY REALTY"},
    {"symbol": "^CNXENERGY", "name": "NIFTY ENERGY"},
]


# In-memory cache
_cache = {}


class MarketDataService:
    async def cache_set(self, key: str, value: dict, ttl: int = 60):
        _cache[key] = {
            "value": value,
            "expires": time.time() + ttl
        }

    async def cache_get(self, key: str) -> Optional[dict]:
        item = _cache.get(key)
        if item and time.time() < item["expires"]:
            return item["value"]
        if item:
            del _cache[key]
        return None

    def is_market_open(self) -> bool:
        now = datetime.now(IST)
        if now.weekday() >= 5:  # Saturday/Sunday
            return False
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close

    _semaphore = asyncio.Semaphore(5)

    async def fetch_live_quote(self, symbol: str) -> Optional[Dict]:
        """Fetch latest price for a symbol."""
        cache_key = f"quote:{symbol}"
        cached = await self.cache_get(cache_key)
        if cached:
            return cached

        async with self._semaphore:
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, self._fetch_quote_sync, symbol)
                if data:
                    await self.cache_set(cache_key, data, ttl=60)
                return data
            except Exception as e:
                print(f"Error fetching quote for {symbol}: {e}")
                return None

    def _fetch_quote_sync(self, symbol: str) -> Optional[Dict]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            hist = ticker.history(period="2d", interval="1d")
            if hist.empty:
                return None

            prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else float(hist["Close"].iloc[-1])
            current = float(hist["Close"].iloc[-1])
            change = current - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0

            return {
                "symbol": symbol,
                "price": round(current, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "prev_close": round(prev_close, 2),
                "volume": int(hist["Volume"].iloc[-1]),
                "high": round(float(hist["High"].iloc[-1]), 2),
                "low": round(float(hist["Low"].iloc[-1]), 2),
                "open": round(float(hist["Open"].iloc[-1]), 2),
                "timestamp": datetime.now(IST).isoformat(),
            }
        except Exception as e:
            print(f"Sync fetch error for {symbol}: {e}")
            return None

    async def fetch_all_quotes(self) -> List[Dict]:
        """Fetch live quotes for all NIFTY 50 stocks."""
        symbols = [s["symbol"] for s in NIFTY50_STOCKS]
        tasks = [self.fetch_live_quote(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        quotes = []
        for i, result in enumerate(results):
            if isinstance(result, dict):
                stock_meta = NIFTY50_STOCKS[i]
                result.update({"name": stock_meta["name"], "sector": stock_meta["sector"]})
                quotes.append(result)
        return quotes

    async def fetch_index_quotes(self) -> List[Dict]:
        """Fetch quotes for major indices."""
        tasks = [self.fetch_live_quote(idx["symbol"]) for idx in INDICES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        indices = []
        for i, result in enumerate(results):
            if isinstance(result, dict):
                result["name"] = INDICES[i]["name"]
                indices.append(result)
        return indices

    async def fetch_ohlcv(
        self, symbol: str, period: str = "6mo", interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV candlestick data."""
        cache_key = f"ohlcv:{symbol}:{period}:{interval}"
        cached = await self.cache_get(cache_key)
        if cached:
            return pd.DataFrame(cached)

        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, lambda: yf.download(symbol, period=period, interval=interval, progress=False)
            )
            if df.empty:
                return None

            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.rename(columns=str.lower)
            df["timestamp"] = df["date"].astype(str) if "date" in df.columns else df.index.astype(str)

            ttl = 300 if interval == "1d" else 60
            await self.cache_set(cache_key, df.to_dict(orient="records"), ttl=ttl)
            return df
        except Exception as e:
            print(f"Error fetching OHLCV for {symbol}: {e}")
            return None

    async def get_market_breadth(self) -> Dict:
        """Calculate overall market breadth."""
        quotes = await self.fetch_all_quotes()
        advancing = sum(1 for q in quotes if q.get("change_pct", 0) > 0)
        declining = sum(1 for q in quotes if q.get("change_pct", 0) < 0)
        unchanged = len(quotes) - advancing - declining
        return {
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "advance_decline_ratio": round(advancing / max(declining, 1), 2),
            "total": len(quotes),
        }


market_data_service = MarketDataService()
