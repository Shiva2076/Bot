from typing import Dict, List, Tuple

from schemas.premarket import IndexMove
from schemas.trading import Tick
from services.premarket.sentiment_classifier import SentimentClassifier
from services.trading.failover_market_data import FailoverMarketData

GLOBAL_INDICES: Tuple[Tuple[str, str], ...] = (
    ("^IXIC", "NASDAQ Composite"),
    ("^GSPC", "S&P 500"),
    ("^DJI", "Dow Jones"),
    ("^N225", "Nikkei 225"),
    ("^HSI", "Hang Seng"),
)


class GlobalMarketsCollector:
    def __init__(self, market_data: FailoverMarketData, classifier: SentimentClassifier):
        self._market_data = market_data
        self._classifier = classifier

    async def collect(self) -> List[IndexMove]:
        symbols = [symbol for symbol, _ in GLOBAL_INDICES]
        ticks = await self._market_data.get_ticks(symbols)
        names: Dict[str, str] = {symbol: name for symbol, name in GLOBAL_INDICES}
        return [
            IndexMove(
                symbol=symbol,
                name=names[symbol],
                last=tick.ltp,
                change_pct=tick.change_pct,
                sentiment=self._classifier.from_change_pct(tick.change_pct),
                timestamp=tick.timestamp,
                source=tick.provider,
            )
            for symbol, tick in ticks.items()
            if isinstance(tick, Tick)
        ]
