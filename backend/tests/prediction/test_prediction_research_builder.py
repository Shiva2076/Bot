from datetime import date, datetime, timezone

import pytest

from models.prediction_log import PredictionLogRecord
from schemas.costs import CostConfig
from schemas.prediction import PredictionDirection
from schemas.prediction_log import DirectionResult
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.prediction.prediction_outcome_calculator import PredictionOutcomeCalculator
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.research.prediction_research_builder import PredictionResearchBuilder


class _NoPremiums:
    async def premiums_for_horizons(self, **kwargs):
        return {15: None, 30: None, 60: None}


@pytest.mark.asyncio
async def test_build_one_score_implied_put_hit():
    costs = PaperCostCalculator(
        CostConfig(
            brokerage_pct=0.03,
            brokerage_flat=20.0,
            exchange_txn_pct=0.00345,
            sebi_pct=0.0001,
            stamp_duty_buy_pct=0.015,
            stt_sell_pct=0.025,
            gst_pct=18.0,
            slippage_bps=5.0,
        )
    )
    builder = PredictionResearchBuilder(
        scorer=PredictionScorer(),
        outcome_calculator=PredictionOutcomeCalculator(0.05, costs),
        costs=costs,
    )
    row = PredictionLogRecord(
        id=1,
        underlying="NIFTY",
        expiry=date(2026, 10, 27),
        spot=25000.0,
        lot_size=65,
        direction=PredictionDirection.WAIT.value,
        score=-0.432,
        confidence=70.0,
        session_label="MID_MORNING",
        is_expiry_day=False,
        scorer_version="v1",
        data_version="v1",
        factors=[],
        factor_scores={},
        metrics={},
        gate_reason="PREMARKET_WAIT",
        premarket_wait_trigger="LARGE_GAP",
        predicted_at=datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc),
        outcome_status="PARTIAL",
        spot_change_pct_15m=-0.2,
        spot_change_pct_30m=None,
        spot_change_pct_60m=None,
    )
    payload = await builder._build_one(row, _NoPremiums())
    assert payload is not None
    assert payload.implied_direction == PredictionDirection.PUT
    assert payload.spot_result_15m == DirectionResult.HIT
    assert payload.hypothetical is True
    assert payload.premarket_wait_trigger == "LARGE_GAP"
