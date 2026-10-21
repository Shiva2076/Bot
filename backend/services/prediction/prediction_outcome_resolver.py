from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.prediction_log import PredictionLogRecord
from repositories.prediction_log_repository import PredictionLogRepository
from schemas.options import OptionUnderlying
from schemas.prediction import PredictionDirection
from schemas.prediction_log import HorizonMinutes, HorizonObservation
from services.options.option_chain_service import UNDERLYING_SPOT_SYMBOLS
from services.prediction.prediction_outcome_calculator import PredictionOutcomeCalculator
from services.trading.failover_market_data import FailoverMarketData


class PredictionOutcomeResolver:
    def __init__(
        self,
        market_data: FailoverMarketData,
        calculator: PredictionOutcomeCalculator,
    ):
        self._market_data = market_data
        self._calculator = calculator

    async def resolve_due(self, session: AsyncSession, now: datetime) -> int:
        repo = PredictionLogRepository(session)
        rows = await repo.list_unresolved()
        resolved = 0
        for row in rows:
            if await self._resolve_row(repo, row, now):
                resolved += 1
        return resolved

    async def _resolve_row(
        self,
        repo: PredictionLogRepository,
        row: PredictionLogRecord,
        now: datetime,
    ) -> bool:
        predicted_at = row.predicted_at
        if predicted_at.tzinfo is None:
            predicted_at = predicted_at.replace(tzinfo=timezone.utc)
        due_horizons = [
            minutes
            for minutes in HorizonMinutes
            if not repo.horizon_filled(row, minutes)
            and now >= predicted_at + timedelta(minutes=minutes.value)
        ]
        if not due_horizons:
            return False
        spot_symbol = UNDERLYING_SPOT_SYMBOLS[OptionUnderlying(row.underlying)]
        symbols: List[str] = [spot_symbol]
        if row.contract_symbol:
            symbols.append(row.contract_symbol)
        ticks = await self._market_data.get_ticks(symbols)
        if spot_symbol not in ticks:
            return False
        later_spot = ticks[spot_symbol].ltp
        later_premium: Optional[float] = None
        if row.contract_symbol and row.contract_symbol in ticks:
            later_premium = ticks[row.contract_symbol].ltp
        for minutes in due_horizons:
            outcome = self._calculator.build(HorizonObservation(
                minutes=minutes,
                direction=PredictionDirection(row.direction),
                entry_spot=row.spot,
                later_spot=later_spot,
                entry_premium=row.entry_premium,
                later_premium=later_premium,
                lot_size=row.lot_size,
            ))
            await repo.apply_horizon(row, outcome, now)
        return True
