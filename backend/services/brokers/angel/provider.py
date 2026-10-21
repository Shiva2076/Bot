import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytz

from schemas.angel import (
    AngelCandleRequest,
    AngelCandleResponse,
    AngelInstrumentRef,
    AngelQuote,
    AngelQuoteRequest,
    AngelQuoteResponse,
)
from schemas.trading import Candle, CandleInterval, Tick
from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.brokers.angel.quote_mapper import AngelQuoteMapper
from services.brokers.angel.session import AngelSession
from services.trading.errors import MarketDataUnavailableError
from services.trading.market_data_provider import MarketDataProvider

QUOTE_PATH = "/rest/secure/angelbroking/market/v1/quote/"
CANDLE_PATH = "/rest/secure/angelbroking/historical/v1/getCandleData"
QUOTE_BATCH_SIZE = 50
CANDLE_CACHE_SECONDS = 30.0
CANDLE_SETTINGS: Dict[CandleInterval, Tuple[str, int]] = {
    CandleInterval.ONE_MINUTE: ("ONE_MINUTE", 3),
    CandleInterval.FIVE_MINUTES: ("FIVE_MINUTE", 7),
    CandleInterval.FIFTEEN_MINUTES: ("FIFTEEN_MINUTE", 7),
    CandleInterval.ONE_DAY: ("ONE_DAY", 60),
}
IST = pytz.timezone("Asia/Kolkata")


class AngelProvider(MarketDataProvider):
    def __init__(
        self,
        session: AngelSession,
        master: AngelInstrumentMaster,
        mapper: AngelQuoteMapper,
        quote_cache_seconds: float,
    ):
        self._session = session
        self._master = master
        self._mapper = mapper
        self._quote_cache_seconds = quote_cache_seconds
        self._quotes: Dict[str, Tuple[float, AngelQuote]] = {}
        self._candles: Dict[Tuple[str, CandleInterval], Tuple[float, List[Candle]]] = {}

    @property
    def name(self) -> str:
        return "ANGEL"

    async def get_tick(self, symbol: str) -> Optional[Tick]:
        return (await self.get_ticks([symbol])).get(symbol)

    async def get_ticks(self, symbols: List[str]) -> Dict[str, Tick]:
        quotes = await self.get_quotes(symbols)
        return {
            symbol: self._mapper.to_tick(symbol, quote, self.name, self.quote_fetched_at(symbol))
            for symbol, quote in quotes.items()
        }

    def quote_fetched_at(self, symbol: str) -> datetime:
        cached = self._quotes.get(symbol)
        if cached is None:
            return datetime.now(pytz.utc)
        return datetime.fromtimestamp(cached[0], pytz.utc)

    async def get_quotes(self, symbols: List[str]) -> Dict[str, AngelQuote]:
        now = time.time()
        fresh = {s: c[1] for s, c in self._quotes.items() if s in symbols and now - c[0] < self._quote_cache_seconds}
        missing = [s for s in set(symbols) if s not in fresh]
        fetched = await self._fetch_quotes(missing)
        for symbol, quote in fetched.items():
            self._quotes[symbol] = (now, quote)
        return {**fresh, **fetched}

    async def get_candles(self, symbol: str, interval: CandleInterval) -> List[Candle]:
        key = (symbol, interval)
        cached = self._candles.get(key)
        if cached and time.time() - cached[0] < CANDLE_CACHE_SECONDS:
            return cached[1]
        ref = await self._master.ref_for(symbol)
        if ref is None:
            return []
        angel_interval, days = CANDLE_SETTINGS[interval]
        now = datetime.now(IST)
        request = AngelCandleRequest(
            exchange=ref.exchange,
            symboltoken=ref.token,
            interval=angel_interval,
            fromdate=(now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M"),
            todate=now.strftime("%Y-%m-%d %H:%M"),
        )
        response = AngelCandleResponse.model_validate(await self._session.post(CANDLE_PATH, request))
        if not response.status or not response.data:
            raise MarketDataUnavailableError(f"Angel One candles failed: {response.message}")
        candles = [self._mapper.to_candle(row) for row in response.data]
        self._candles[key] = (time.time(), candles)
        return candles

    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, AngelQuote]:
        if not symbols:
            return {}
        refs = await self._resolve(symbols)
        by_exchange: Dict[str, List[str]] = defaultdict(list)
        for ref in refs.values():
            by_exchange[ref.exchange].append(ref.token)
        batches = [
            {exchange: tokens[i:i + QUOTE_BATCH_SIZE]}
            for exchange, tokens in by_exchange.items()
            for i in range(0, len(tokens), QUOTE_BATCH_SIZE)
        ]
        responses = await asyncio.gather(*(self._quote_batch(batch) for batch in batches))
        symbol_by_ref = {(ref.exchange, ref.token): symbol for symbol, ref in refs.items()}
        return {
            symbol_by_ref[(quote.exchange, quote.symbol_token)]: quote
            for quotes in responses
            for quote in quotes
            if (quote.exchange, quote.symbol_token) in symbol_by_ref
        }

    async def _resolve(self, symbols: List[str]) -> Dict[str, AngelInstrumentRef]:
        refs = await asyncio.gather(*(self._master.ref_for(s) for s in symbols))
        return {symbol: ref for symbol, ref in zip(symbols, refs) if ref}

    async def _quote_batch(self, exchange_tokens: Dict[str, List[str]]) -> List[AngelQuote]:
        request = AngelQuoteRequest(mode="FULL", exchange_tokens=exchange_tokens)
        response = AngelQuoteResponse.model_validate(await self._session.post(QUOTE_PATH, request))
        if not response.status or response.data is None:
            raise MarketDataUnavailableError(f"Angel One quote failed: {response.message}")
        return response.data.fetched
