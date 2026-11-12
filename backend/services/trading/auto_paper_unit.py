from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.paper_signal import PaperSignalRecord
from repositories.paper_signal_repository import PaperSignalRepository
from repositories.trade_repository import TradeRepository
from schemas.options import OptionUnderlying
from schemas.order_entry import EntryOrigin
from schemas.paper_engine import PaperExecutionStatus, PaperLifecycleEvent, PaperSignalCreate, PaperSignalEventRecord
from schemas.personal_trade import TradeExitRequest
from schemas.trading import ExitReason, MarketOrderRequest
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.trade_mapper import PersonalTradeMapper


class SqlAutoPaperUnit:
    """Postgres-backed unit of work for AutoPaperEngine; one session, committed explicitly."""

    def __init__(
        self,
        session: AsyncSession,
        order_service_factory: Callable,
        mapper: PersonalTradeMapper,
        costs: PaperCostCalculator,
    ):
        self.session = session
        self._trades = TradeRepository(session)
        self._signals = PaperSignalRepository(session)
        self._orders = order_service_factory(session)
        self._mapper = mapper
        self._costs = costs

    async def open_auto_trades(self, for_update: bool = False) -> list:
        trades = await self._trades.list_open(for_update=for_update)
        return [t for t in trades if t.paper_signal_id is not None]

    async def entries_on(self, underlying: OptionUnderlying, day: date) -> int:
        table = PaperSignalRecord
        result = await self.session.execute(
            select(func.count()).select_from(table).where(
                table.session_date == day,
                table.underlying == underlying.value,
                table.execution_status == PaperExecutionStatus.EXECUTED.value,
            )
        )
        return int(result.scalar_one())

    async def add_signal(self, data: PaperSignalCreate) -> int:
        return (await self._signals.add(data)).id

    async def update_signal(self, signal_id: int, **changes) -> None:
        await self._signals.update_status(signal_id, **changes)

    async def place(self, request: MarketOrderRequest, signal_id: int):
        return await self._orders.place(request, EntryOrigin.AUTO_PAPER, paper_signal_id=signal_id)

    async def close_trade(self, trade, exit_price: float, at: datetime, reason: ExitReason) -> None:
        self._mapper.apply_exit(
            trade, TradeExitRequest(exit_price=exit_price, exit_time=at, exit_reason=reason.value), self._costs
        )
        if trade.paper_signal_id is not None:
            await self._signals.append_event(trade.paper_signal_id, PaperSignalEventRecord(
                timestamp=at, event_type=PaperLifecycleEvent.PAPER_POSITION_CLOSED,
                details={"exit_reason": reason.value, "exit_price": exit_price, "pnl": trade.pnl},
            ))
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


def sql_unit_factory(session_factory: Callable, order_service_factory: Callable,
                     mapper: PersonalTradeMapper, costs: PaperCostCalculator) -> Callable:
    @asynccontextmanager
    async def units():
        async with session_factory() as session:
            yield SqlAutoPaperUnit(session, order_service_factory, mapper, costs)
    return units
