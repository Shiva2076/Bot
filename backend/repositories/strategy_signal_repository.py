from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.strategy_signal import StrategySignalRecord
from schemas.orb import OrbSignal


class StrategySignalRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(
        self,
        strategy: str,
        signal: OrbSignal,
        executed: bool,
        trade_id: Optional[int],
        gate_reasons: List[str],
    ) -> StrategySignalRecord:
        row = StrategySignalRecord(
            strategy=strategy,
            symbol=signal.symbol,
            session_date=signal.session_date,
            decision=signal.decision.value,
            action=None if signal.action is None else signal.action.value,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            quantity=signal.quantity,
            signal_time=signal.signal_time,
            rejection_reason=signal.rejection_reason or ("; ".join(gate_reasons) if gate_reasons else None),
            executed="YES" if executed else "NO",
            trade_id=trade_id,
            outcome=None,
            inputs=signal.inputs,
            reasons=signal.reasons,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_day(self, strategy: str, session_date: date) -> List[StrategySignalRecord]:
        result = await self._session.execute(
            select(StrategySignalRecord).where(
                StrategySignalRecord.strategy == strategy,
                StrategySignalRecord.session_date == session_date,
            )
        )
        return list(result.scalars().all())
