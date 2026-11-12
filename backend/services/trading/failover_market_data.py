import asyncio
from typing import Dict, List, Optional

from schemas.trading import CandleInterval, CandleSeries, Tick
from services.trading.errors import MarketDataUnavailableError
from services.trading.market_data_provider import MarketDataProvider

PROVIDER_CALL_TIMEOUT_SECONDS = 8.0


class FailoverMarketData:
    def __init__(
        self,
        providers: List[MarketDataProvider],
        provider_timeout_seconds: float = PROVIDER_CALL_TIMEOUT_SECONDS,
    ):
        self._providers = providers
        self._provider_timeout_seconds = provider_timeout_seconds

    async def get_tick(self, symbol: str) -> Tick:
        ticks = await self.get_ticks([symbol])
        if symbol not in ticks:
            raise MarketDataUnavailableError(f"No provider returned a price for {symbol}")
        return ticks[symbol]

    async def get_preferred_tick(self, symbol: str) -> Tick:
        """Preferred provider only (Angel). Used for prediction freshness — no Yahoo fill."""
        if not self._providers:
            raise MarketDataUnavailableError(f"No provider configured for {symbol}")
        primary = self._providers[0]
        last_error: Optional[BaseException] = None
        for attempt in range(2):
            try:
                result = await self._call(primary.get_ticks([symbol]))
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.35)
                continue
            if isinstance(result, Exception):
                last_error = result
                if attempt == 0:
                    await asyncio.sleep(0.35)
                continue
            tick = result.get(symbol)
            if tick is None:
                last_error = MarketDataUnavailableError(
                    f"{primary.name} did not return a price for {symbol}"
                )
                if attempt == 0:
                    await asyncio.sleep(0.35)
                continue
            return tick
        raise MarketDataUnavailableError(
            f"{primary.name} did not return a price for {symbol}"
        ) from last_error

    async def get_ticks(self, symbols: List[str]) -> Dict[str, Tick]:
        if not symbols:
            return {}
        results = await asyncio.gather(
            *(self._call(p.get_ticks(symbols)) for p in self._providers),
            return_exceptions=True,
        )
        merged: Dict[str, Tick] = {}
        for provider, result in zip(self._providers, results):
            if isinstance(result, Exception):
                print(f"{provider.name} ticks failed: {result}")
                continue
            for symbol, tick in result.items():
                merged[symbol] = self._prefer_tick(merged.get(symbol), tick)
        return merged

    async def get_candles(self, symbol: str, interval: CandleInterval) -> CandleSeries:
        results = await asyncio.gather(
            *(self._call(p.get_candles(symbol, interval)) for p in self._providers),
            return_exceptions=True,
        )
        for provider, result in zip(self._providers, results):
            if isinstance(result, list) and result:
                return CandleSeries(symbol=symbol, interval=interval, provider=provider.name, candles=result)
        raise MarketDataUnavailableError(f"No provider returned candles for {symbol}")

    async def _call(self, coro):
        return await asyncio.wait_for(coro, timeout=self._provider_timeout_seconds)

    @staticmethod
    def _prefer_tick(current: Optional[Tick], candidate: Tick) -> Tick:
        """Keep preferred-provider tick; never replace exchange-verified with fetch-only."""
        if current is None:
            return candidate
        if current.exchange_timestamp is not None:
            return current
        if candidate.exchange_timestamp is not None:
            return candidate
        return current
