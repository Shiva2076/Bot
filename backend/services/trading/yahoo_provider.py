import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pytz
import yfinance as yf

from schemas.trading import Candle, CandleInterval, Tick
from services.trading.market_data_provider import MarketDataProvider

CANDLE_PERIODS: Dict[CandleInterval, str] = {
    CandleInterval.ONE_MINUTE: "1d",
    CandleInterval.FIVE_MINUTES: "5d",
    CandleInterval.FIFTEEN_MINUTES: "5d",
    CandleInterval.ONE_DAY: "60d",
}
CANDLE_CACHE_SECONDS = 30.0
YAHOO_INDEX_PREFIX = "^"
YAHOO_NSE_SUFFIX = ".NS"


class YahooProvider(MarketDataProvider):
    def __init__(self, tick_cache_seconds: float):
        self._tick_cache_seconds = tick_cache_seconds
        self._ticks: Dict[str, Tuple[float, Tick]] = {}
        self._candles: Dict[Tuple[str, CandleInterval], Tuple[float, List[Candle]]] = {}

    @property
    def name(self) -> str:
        return "YAHOO"

    async def get_ticks(self, symbols: List[str]) -> Dict[str, Tick]:
        ticks = await asyncio.gather(*(self.get_tick(s) for s in set(symbols)))
        return {tick.symbol: tick for tick in ticks if tick}

    async def get_tick(self, symbol: str) -> Optional[Tick]:
        if not self._supports(symbol):
            return None
        cached = self._ticks.get(symbol)
        if cached and time.time() - cached[0] < self._tick_cache_seconds:
            return cached[1]
        tick = await asyncio.get_running_loop().run_in_executor(None, self._fetch_tick, symbol)
        if tick:
            self._ticks[symbol] = (time.time(), tick)
        return tick

    async def get_candles(self, symbol: str, interval: CandleInterval) -> List[Candle]:
        if not self._supports(symbol):
            return []
        key = (symbol, interval)
        cached = self._candles.get(key)
        if cached and time.time() - cached[0] < CANDLE_CACHE_SECONDS:
            return cached[1]
        candles = await asyncio.get_running_loop().run_in_executor(None, self._fetch_candles, symbol, interval)
        if candles:
            self._candles[key] = (time.time(), candles)
        return candles

    def _supports(self, symbol: str) -> bool:
        return symbol.startswith(YAHOO_INDEX_PREFIX) or symbol.endswith(YAHOO_NSE_SUFFIX)

    def _fetch_tick(self, symbol: str) -> Optional[Tick]:
        try:
            info = yf.Ticker(symbol).fast_info
            ltp = float(info.last_price)
            prev_close = float(info.previous_close)
        except Exception as e:
            print(f"Yahoo tick error for {symbol}: {e}")
            return None
        change = ltp - prev_close
        fetched_at = datetime.now(pytz.utc)
        return Tick(
            symbol=symbol,
            ltp=round(ltp, 2),
            prev_close=round(prev_close, 2),
            change=round(change, 2),
            change_pct=round(change / prev_close * 100, 2) if prev_close else 0.0,
            timestamp=fetched_at,
            provider=self.name,
            fetched_at=fetched_at,
            exchange_timestamp=None,
        )

    def _fetch_candles(self, symbol: str, interval: CandleInterval) -> List[Candle]:
        try:
            df = yf.Ticker(symbol).history(period=CANDLE_PERIODS[interval], interval=interval.value)
        except Exception as e:
            print(f"Yahoo candles error for {symbol}: {e}")
            return []
        return [
            Candle(
                time=int(ts.timestamp()),
                open=round(float(row.Open), 2),
                high=round(float(row.High), 2),
                low=round(float(row.Low), 2),
                close=round(float(row.Close), 2),
                volume=float(row.Volume),
            )
            for ts, row in zip(df.index, df.itertuples())
        ]
