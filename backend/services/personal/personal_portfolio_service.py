from datetime import datetime

import pytz

from repositories.trade_repository import TradeRepository
from schemas.personal_trade import PersonalHistoryResponse, TradeStatus
from services.personal.history_aggregator import PersonalHistoryAggregator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.failover_market_data import FailoverMarketData


class PersonalPortfolioService:
    def __init__(
        self,
        repository: TradeRepository,
        mapper: PersonalTradeMapper,
        aggregator: PersonalHistoryAggregator,
        market_data: FailoverMarketData,
    ):
        self._repository = repository
        self._mapper = mapper
        self._aggregator = aggregator
        self._market_data = market_data

    async def get_history(self) -> PersonalHistoryResponse:
        trades = await self._repository.list_all()
        ticks = await self._market_data.get_ticks([t.symbol for t in trades if t.status == TradeStatus.OPEN.value])
        views = [self._mapper.to_view(t, ticks[t.symbol].ltp if t.symbol in ticks else None) for t in trades]
        return PersonalHistoryResponse(
            as_of=datetime.now(pytz.utc),
            summary=self._aggregator.build_summary(views),
            open_positions=[v for v in views if v.status == TradeStatus.OPEN],
            days=self._aggregator.build_days(views),
        )
