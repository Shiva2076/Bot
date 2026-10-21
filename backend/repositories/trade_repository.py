from datetime import date, datetime, time
from typing import List, Optional

import pytz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import Trade
from schemas.personal_trade import TradeStatus, TradeType
from services.personal.errors import TradeNotFoundError

IST = pytz.timezone("Asia/Kolkata")


class TradeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

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

    async def list_open(self, trade_type: Optional[TradeType] = None) -> List[Trade]:
        query = select(Trade).where(Trade.status == TradeStatus.OPEN.value)
        if trade_type is not None:
            query = query.where(Trade.trade_type == trade_type.value)
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
