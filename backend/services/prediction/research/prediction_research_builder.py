from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.prediction_log import PredictionLogRecord
from repositories.prediction_research_repository import PredictionResearchRepository
from schemas.options import OptionUnderlying
from schemas.personal_trade import TradeAction
from schemas.prediction import PredictionDirection
from schemas.prediction_log import DirectionResult
from schemas.prediction_research import PredictionResearchOutcomeCreate
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.prediction.prediction_outcome_calculator import PredictionOutcomeCalculator
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.research.hypothetical_premium_resolver import HypotheticalPremiumResolver

HORIZONS = (15, 30, 60)


class PredictionResearchBuilder:
    """
    Offline research builder for gated prediction rows.
    Must never be imported by live trading/prediction request paths.
    """

    def __init__(
        self,
        scorer: PredictionScorer,
        outcome_calculator: PredictionOutcomeCalculator,
        costs: PaperCostCalculator,
    ):
        self._scorer = scorer
        self._outcomes = outcome_calculator
        self._costs = costs

    async def rebuild(self, session: AsyncSession) -> int:
        repo = PredictionResearchRepository(session)
        premiums = HypotheticalPremiumResolver(session)
        written = 0
        for row in await repo.list_gated_logs_for_research():
            payload = await self._build_one(row, premiums)
            if payload is None:
                continue
            await repo.upsert(payload)
            written += 1
        return written

    async def _build_one(
        self,
        row: PredictionLogRecord,
        premiums: HypotheticalPremiumResolver,
    ) -> Optional[PredictionResearchOutcomeCreate]:
        implied = self._scorer.direction(row.score)
        spot_15 = self._spot_result(implied, row.spot_change_pct_15m)
        spot_30 = self._spot_result(implied, row.spot_change_pct_30m)
        spot_60 = self._spot_result(implied, row.spot_change_pct_60m)
        pnl_map = await premiums.premiums_for_horizons(
            underlying=OptionUnderlying(row.underlying),
            expiry=row.expiry,
            predicted_at=row.predicted_at,
            implied_direction=implied,
            lot_size=row.lot_size,
            horizons_minutes=list(HORIZONS),
        )
        return PredictionResearchOutcomeCreate(
            prediction_log_id=row.id,
            underlying=OptionUnderlying(row.underlying),
            predicted_at=row.predicted_at,
            gate_reason=row.gate_reason,
            premarket_wait_trigger=row.premarket_wait_trigger,
            score=row.score,
            implied_direction=implied,
            spot_result_15m=spot_15,
            spot_result_30m=spot_30,
            spot_result_60m=spot_60,
            spot_change_pct_15m=row.spot_change_pct_15m,
            spot_change_pct_30m=row.spot_change_pct_30m,
            spot_change_pct_60m=row.spot_change_pct_60m,
            hypothetical_net_pnl_15m=self._pnl(pnl_map.get(15)),
            hypothetical_net_pnl_30m=self._pnl(pnl_map.get(30)),
            hypothetical_net_pnl_60m=self._pnl(pnl_map.get(60)),
            hypothetical=True,
        )

    def _spot_result(
        self,
        implied: PredictionDirection,
        spot_change_pct: Optional[float],
    ) -> Optional[DirectionResult]:
        if spot_change_pct is None:
            return None
        return self._outcomes.direction_result(implied, spot_change_pct)

    def _pnl(self, pair) -> Optional[float]:
        if pair is None:
            return None
        entry_premium, later_premium, lot_size = pair
        return self._costs.net_pnl(TradeAction.BUY, entry_premium, later_premium, lot_size)
