from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from schemas.trading import Candle, CandleInterval, Tick


class MarketDataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def get_tick(self, symbol: str) -> Optional[Tick]:
        ...

    @abstractmethod
    async def get_ticks(self, symbols: List[str]) -> Dict[str, Tick]:
        ...

    @abstractmethod
    async def get_candles(self, symbol: str, interval: CandleInterval) -> List[Candle]:
        ...
