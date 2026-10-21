from typing import Optional

from schemas.personal_trade import TradeAction
from schemas.prediction import PredictionDirection
from schemas.prediction_log import DirectionResult, HorizonObservation, HorizonOutcome
from services.costs.paper_cost_calculator import PaperCostCalculator


class PredictionOutcomeCalculator:
    def __init__(self, flat_band_pct: float, costs: PaperCostCalculator):
        self._flat_band_pct = flat_band_pct
        self._costs = costs

    def build(self, observation: HorizonObservation) -> HorizonOutcome:
        spot_change_pct = self._pct_change(observation.entry_spot, observation.later_spot)
        premium_change_pct = None
        net_pnl = None
        if observation.entry_premium is not None and observation.later_premium is not None and observation.entry_premium > 0:
            premium_change_pct = self._pct_change(observation.entry_premium, observation.later_premium)
            net_pnl = self._net_pnl_per_lot(observation)
        return HorizonOutcome(
            minutes=observation.minutes,
            spot=observation.later_spot,
            spot_change_pct=spot_change_pct,
            direction_result=self.direction_result(observation.direction, spot_change_pct),
            premium=observation.later_premium,
            premium_change_pct=premium_change_pct,
            net_pnl_per_lot=net_pnl,
        )

    def direction_result(self, direction: PredictionDirection, spot_change_pct: float) -> DirectionResult:
        if direction in (
            PredictionDirection.NO_TRADE,
            PredictionDirection.WAIT,
            PredictionDirection.MARKET_CLOSED,
            PredictionDirection.STALE_DATA,
            PredictionDirection.UNKNOWN_FRESHNESS,
        ):
            return DirectionResult.NA
        if abs(spot_change_pct) < self._flat_band_pct:
            return DirectionResult.FLAT
        if direction == PredictionDirection.CALL:
            return DirectionResult.HIT if spot_change_pct > 0 else DirectionResult.MISS
        return DirectionResult.HIT if spot_change_pct < 0 else DirectionResult.MISS

    def _net_pnl_per_lot(self, observation: HorizonObservation) -> Optional[float]:
        if observation.lot_size is None:
            return None
        return self._costs.net_pnl(
            TradeAction.BUY, observation.entry_premium, observation.later_premium, observation.lot_size
        )

    @staticmethod
    def _pct_change(start: float, end: float) -> float:
        return round((end - start) / start * 100.0, 4)
