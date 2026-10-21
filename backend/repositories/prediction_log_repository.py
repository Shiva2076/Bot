from datetime import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.prediction_log import PRE_FIX_DATA_VERSION, PredictionLogRecord
from schemas.prediction_log import HorizonOutcome, HorizonMinutes, OutcomeStatus, PredictionLogCreate


class PredictionLogRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, payload: PredictionLogCreate) -> PredictionLogRecord:
        row = PredictionLogRecord(
            underlying=payload.underlying.value,
            expiry=payload.expiry,
            spot=payload.spot,
            lot_size=payload.lot_size,
            direction=payload.direction.value,
            score=payload.score,
            confidence=payload.confidence,
            session_label=payload.session_label,
            is_expiry_day=payload.is_expiry_day,
            scorer_version=payload.scorer_version,
            data_version=payload.data_version,
            factors=payload.factors,
            factor_scores=payload.factor_scores,
            metrics=payload.metrics,
            cluster_scores=payload.cluster_scores,
            regime=payload.regime,
            shadow_features=payload.shadow_features,
            contract_symbol=payload.contract_symbol,
            contract_strike=payload.contract_strike,
            contract_option_type=None
            if payload.contract_option_type is None
            else payload.contract_option_type.value,
            entry_premium=payload.entry_premium,
            predicted_at=payload.predicted_at,
            outcome_status=OutcomeStatus.PENDING.value,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_recent(self, limit: int, exclude_pre_fix: bool) -> List[PredictionLogRecord]:
        query = select(PredictionLogRecord)
        if exclude_pre_fix:
            query = query.where(PredictionLogRecord.data_version != PRE_FIX_DATA_VERSION)
        result = await self._session.execute(
            query.order_by(PredictionLogRecord.predicted_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_unresolved(self) -> List[PredictionLogRecord]:
        result = await self._session.execute(
            select(PredictionLogRecord).where(
                PredictionLogRecord.outcome_status != OutcomeStatus.COMPLETE.value
            )
        )
        return list(result.scalars().all())

    async def apply_horizon(
        self,
        row: PredictionLogRecord,
        outcome: HorizonOutcome,
        resolved_at: datetime,
    ) -> None:
        direction_result = outcome.direction_result.value
        if outcome.minutes == HorizonMinutes.M15:
            row.spot_15m = outcome.spot
            row.spot_change_pct_15m = outcome.spot_change_pct
            row.direction_result_15m = direction_result
            row.premium_15m = outcome.premium
            row.premium_change_pct_15m = outcome.premium_change_pct
            row.net_pnl_15m = outcome.net_pnl_per_lot
        elif outcome.minutes == HorizonMinutes.M30:
            row.spot_30m = outcome.spot
            row.spot_change_pct_30m = outcome.spot_change_pct
            row.direction_result_30m = direction_result
            row.premium_30m = outcome.premium
            row.premium_change_pct_30m = outcome.premium_change_pct
            row.net_pnl_30m = outcome.net_pnl_per_lot
        else:
            row.spot_60m = outcome.spot
            row.spot_change_pct_60m = outcome.spot_change_pct
            row.direction_result_60m = direction_result
            row.premium_60m = outcome.premium
            row.premium_change_pct_60m = outcome.premium_change_pct
            row.net_pnl_60m = outcome.net_pnl_per_lot
        row.outcome_status = self._status_after(row).value
        row.outcomes_resolved_at = resolved_at
        await self._session.flush()

    @staticmethod
    def horizon_filled(row: PredictionLogRecord, minutes: HorizonMinutes) -> bool:
        if minutes == HorizonMinutes.M15:
            return row.spot_change_pct_15m is not None
        if minutes == HorizonMinutes.M30:
            return row.spot_change_pct_30m is not None
        return row.spot_change_pct_60m is not None

    @staticmethod
    def _status_after(row: PredictionLogRecord) -> OutcomeStatus:
        filled = sum(1 for minutes in HorizonMinutes if PredictionLogRepository.horizon_filled(row, minutes))
        if filled >= len(HorizonMinutes):
            return OutcomeStatus.COMPLETE
        if filled == 0:
            return OutcomeStatus.PENDING
        return OutcomeStatus.PARTIAL
