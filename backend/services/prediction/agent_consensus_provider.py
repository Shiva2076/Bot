import time
from typing import Dict, Tuple

from agents.orchestrator import generate_signal
from schemas.prediction import AgentConsensus
from services.trading.errors import MarketDataUnavailableError


class AgentConsensusProvider:
    def __init__(self, cache_seconds: float):
        self._cache_seconds = cache_seconds
        self._cache: Dict[str, Tuple[float, AgentConsensus]] = {}

    async def get(self, symbol: str) -> AgentConsensus:
        cached = self._cache.get(symbol)
        if cached and time.time() - cached[0] < self._cache_seconds:
            return cached[1]
        signal = await generate_signal(symbol)
        if signal is None:
            raise MarketDataUnavailableError(f"AI agents could not generate a signal for {symbol}")
        consensus = AgentConsensus.model_validate(signal)
        self._cache[symbol] = (time.time(), consensus)
        return consensus
