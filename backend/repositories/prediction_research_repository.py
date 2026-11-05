from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.prediction_log import PredictionLogRecord
from models.prediction_research_outcome import PredictionResearchOutcomeRecord
from schemas.prediction import PredictionDirection
from schemas.prediction_research import PredictionResearchOutcomeCreate

GATED_DIRECTIONS = {
    PredictionDirection.WAIT.value,
    PredictionDirection.NO_TRADE.value,
    PredictionDirection.STALE_DATA.value,
    PredictionDirection.UNKNOWN_FRESHNESS.value,
    PredictionDirection.MARKET_CLOSED.value,
}


class PredictionResearchRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_gated_logs_for_research(self) -> List[PredictionLogRecord]:
        result = await self._session.execute(
            select(PredictionLogRecord).where(PredictionLogRecord.direction.in_(GATED_DIRECTIONS))
        )
        return list(result.scalars().all())

    async def get_by_prediction_log_id(self, prediction_log_id: int) -> Optional[PredictionResearchOutcomeRecord]:
        result = await self._session.execute(
            select(PredictionResearchOutcomeRecord).where(
                PredictionResearchOutcomeRecord.prediction_log_id == prediction_log_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, payload: PredictionResearchOutcomeCreate) -> PredictionResearchOutcomeRecord:
        existing = await self.get_by_prediction_log_id(payload.prediction_log_id)
        if existing is not None:
            self._apply(existing, payload)
            await self._session.flush()
            return existing
        row = PredictionResearchOutcomeRecord(
            prediction_log_id=payload.prediction_log_id,
            underlying=payload.underlying.value,
            predicted_at=payload.predicted_at,
            gate_reason=payload.gate_reason,
            premarket_wait_trigger=payload.premarket_wait_trigger,
            score=payload.score,
            implied_direction=payload.implied_direction.value,
            spot_result_15m=None if payload.spot_result_15m is None else payload.spot_result_15m.value,
            spot_result_30m=None if payload.spot_result_30m is None else payload.spot_result_30m.value,
            spot_result_60m=None if payload.spot_result_60m is None else payload.spot_result_60m.value,
            spot_change_pct_15m=payload.spot_change_pct_15m,
            spot_change_pct_30m=payload.spot_change_pct_30m,
            spot_change_pct_60m=payload.spot_change_pct_60m,
            hypothetical_net_pnl_15m=payload.hypothetical_net_pnl_15m,
            hypothetical_net_pnl_30m=payload.hypothetical_net_pnl_30m,
            hypothetical_net_pnl_60m=payload.hypothetical_net_pnl_60m,
            hypothetical=payload.hypothetical,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    @staticmethod
    def _apply(row: PredictionResearchOutcomeRecord, payload: PredictionResearchOutcomeCreate) -> None:
        row.underlying = payload.underlying.value
        row.predicted_at = payload.predicted_at
        row.gate_reason = payload.gate_reason
        row.premarket_wait_trigger = payload.premarket_wait_trigger
        row.score = payload.score
        row.implied_direction = payload.implied_direction.value
        row.spot_result_15m = None if payload.spot_result_15m is None else payload.spot_result_15m.value
        row.spot_result_30m = None if payload.spot_result_30m is None else payload.spot_result_30m.value
        row.spot_result_60m = None if payload.spot_result_60m is None else payload.spot_result_60m.value
        row.spot_change_pct_15m = payload.spot_change_pct_15m
        row.spot_change_pct_30m = payload.spot_change_pct_30m
        row.spot_change_pct_60m = payload.spot_change_pct_60m
        row.hypothetical_net_pnl_15m = payload.hypothetical_net_pnl_15m
        row.hypothetical_net_pnl_30m = payload.hypothetical_net_pnl_30m
        row.hypothetical_net_pnl_60m = payload.hypothetical_net_pnl_60m
        row.hypothetical = payload.hypothetical
