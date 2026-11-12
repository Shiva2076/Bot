import logging
from datetime import date, datetime, time
from typing import List, Optional, Union

import pytz
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import Trade
from schemas.options import OptionUnderlying
from schemas.personal_trade import TradeStatus, TradeType
from services.options.option_symbol_parser import OptionSymbolParser
from services.personal.errors import TradeNotFoundError

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
ORDER_PLACEMENT_LOCK_ID = 888001


class TradeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def acquire_order_lock(self) -> None:
        """
        Transactional advisory lock to serialize order placements and prevent
        concurrent requests from bypassing max_open_positions or one-open-position limits.
        Automatically released when the session transaction commits or rolls back.
        """
        try:
            bind = self._session.bind
            dialect_name = getattr(bind.dialect, "name", "") if bind else ""
            if dialect_name == "postgresql":
                await self._session.execute(text(f"SELECT pg_advisory_xact_lock({ORDER_PLACEMENT_LOCK_ID})"))
        except Exception as exc:
            logger.debug(f"Advisory lock skipped or unsupported: {exc}")

    async def add(self, trade: Trade) -> Trade:
        self._session.add(trade)
        await self._session.flush()
        return trade

    async def get(self, trade_id: int) -> Trade:
        trade = await self._session.get(Trade, trade_id)
        if trade is None:
            raise TradeNotFoundError(f"Trade {trade_id} not found")
        return trade

    async def list_all(self) -> List[Trade]:
        result = await self._session.execute(select(Trade).order_by(Trade.entry_time.desc()))
        return list(result.scalars().all())

    async def list_open(
        self,
        trade_type: Optional[TradeType] = None,
        for_update: bool = False,
        skip_locked: bool = True,
    ) -> List[Trade]:
        query = select(Trade).where(Trade.status == TradeStatus.OPEN.value)
        if trade_type is not None:
            query = query.where(Trade.trade_type == trade_type.value)
        if for_update:
            bind = self._session.bind
            dialect_name = getattr(bind.dialect, "name", "") if bind else ""
            if dialect_name == "postgresql":
                query = query.with_for_update(skip_locked=skip_locked)
            else:
                query = query.with_for_update()
        result = await self._session.execute(query.order_by(Trade.entry_time.desc()))
        return list(result.scalars().all())

    async def count_open(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Trade).where(Trade.status == TradeStatus.OPEN.value)
        )
        return int(result.scalar_one())

    async def realized_pnl_on(self, day: date) -> float:
        start = IST.localize(datetime.combine(day, time.min)).astimezone(pytz.utc)
        end = IST.localize(datetime.combine(day, time.max)).astimezone(pytz.utc)
        result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
                Trade.status == TradeStatus.CLOSED.value,
                Trade.exit_time >= start,
                Trade.exit_time <= end,
            )
        )
        return float(result.scalar_one())

    async def open_invested_total(self) -> float:
        result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.invested_amount), 0.0)).where(
                Trade.status == TradeStatus.OPEN.value
            )
        )
        return float(result.scalar_one())

    async def total_realized_pnl(self) -> float:
        result = await self._session.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
                Trade.status == TradeStatus.CLOSED.value
            )
        )
        return float(result.scalar_one())

    async def get_by_paper_signal_id(self, paper_signal_id: int) -> Optional[Trade]:
        result = await self._session.execute(
            select(Trade).where(Trade.paper_signal_id == paper_signal_id)
        )
        return result.scalars().first()

    async def has_open_for_symbol(self, symbol: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(Trade)
            .where(Trade.status == TradeStatus.OPEN.value, Trade.symbol == symbol)
        )
        return int(result.scalar_one()) > 0

    async def count_open_by_underlying(
        self,
        underlying: Union[str, OptionUnderlying],
        parser: Optional[OptionSymbolParser] = None,
    ) -> int:
        trades = await self.list_open()
        if not trades:
            return 0
        p = parser or OptionSymbolParser()
        target = underlying.value if hasattr(underlying, "value") else str(underlying).upper()
        count = 0
        for t in trades:
            parsed = p.parse(t.symbol)
            if parsed is not None and parsed.underlying.value == target:
                count += 1
            elif parsed is None and t.symbol.upper().startswith(target):
                count += 1
        return count


