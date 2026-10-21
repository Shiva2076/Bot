from typing import Optional

from schemas.costs import CostConfig
from schemas.prediction import PredictionDirection
from schemas.prediction_log import DirectionResult, HorizonMinutes, HorizonObservation
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.prediction.prediction_outcome_calculator import PredictionOutcomeCalculator


def _costs(brokerage_flat: float = 0.0) -> PaperCostCalculator:
    return PaperCostCalculator(CostConfig(
        brokerage_pct=0.0,
        brokerage_flat=brokerage_flat,
        exchange_txn_pct=0.0,
        sebi_pct=0.0,
        stamp_duty_buy_pct=0.0,
        stt_sell_pct=0.0,
        gst_pct=0.0,
        slippage_bps=0.0,
    ))


def _calc(brokerage_flat: float = 0.0) -> PredictionOutcomeCalculator:
    return PredictionOutcomeCalculator(flat_band_pct=0.05, costs=_costs(brokerage_flat))


def _observation(
    direction: PredictionDirection,
    later_spot: float,
    later_premium: Optional[float],
    lot_size: Optional[int],
) -> HorizonObservation:
    return HorizonObservation(
        minutes=HorizonMinutes.M15,
        direction=direction,
        entry_spot=25000.0,
        later_spot=later_spot,
        entry_premium=100.0,
        later_premium=later_premium,
        lot_size=lot_size,
    )


def test_call_hit_when_spot_rises():
    outcome = _calc().build(_observation(PredictionDirection.CALL, 25100.0, 120.0, 65))
    assert outcome.direction_result == DirectionResult.HIT
    assert outcome.spot_change_pct > 0
    assert outcome.premium_change_pct == 20.0
    assert outcome.net_pnl_per_lot == 1300.0


def test_net_pnl_is_after_costs():
    outcome = _calc(brokerage_flat=20.0).build(_observation(PredictionDirection.CALL, 25100.0, 120.0, 65))
    assert outcome.net_pnl_per_lot == 1260.0


def test_net_pnl_missing_without_lot_size():
    outcome = _calc().build(_observation(PredictionDirection.CALL, 25100.0, 120.0, None))
    assert outcome.net_pnl_per_lot is None


def test_put_hit_when_spot_falls():
    outcome = _calc().build(_observation(PredictionDirection.PUT, 24800.0, 110.0, 65))
    assert outcome.direction_result == DirectionResult.HIT


def test_flat_inside_band():
    result = _calc().direction_result(PredictionDirection.CALL, 0.01)
    assert result == DirectionResult.FLAT


def test_no_trade_is_na():
    result = _calc().direction_result(PredictionDirection.NO_TRADE, 1.0)
    assert result == DirectionResult.NA


def test_call_miss_when_spot_falls():
    result = _calc().direction_result(PredictionDirection.CALL, -0.2)
    assert result == DirectionResult.MISS
