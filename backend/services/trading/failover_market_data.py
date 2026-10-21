import asyncio
from typing import Dict, List

from schemas.trading import CandleInterval, CandleSeries, Tick
from services.trading.errors import MarketDataUnavailableError
from services.trading.market_data_provider import MarketDataProvider

# Keep Yahoo usable when Angel is stuck downloading the scrip master.
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

    async def get_ticks(self, symbols: List[str]) -> Dict[str, Tick]:
        if not symbols:
            return {}
        results = await asyncio.gather(
            *(self._call(p.get_ticks(symbols)) for p in self._providers),
            return_exceptions=True,
        )
        merged: Dict[str, Tick] = {}
        for provider, result in reversed(list(zip(self._providers, results))):
            if isinstance(result, Exception):
                print(f"{provider.name} ticks failed: {result}")
            else:
                merged.update(result)
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
