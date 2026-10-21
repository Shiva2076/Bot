from typing import List

from schemas.prediction import FactorStatus, PredictionFactor
from services.prediction.breadth_factor_analyzer import BREADTH_WEIGHT
from services.prediction.chain_factor_analyzer import MAX_PAIN_WEIGHT, OI_WALL_WEIGHT, PCR_WEIGHT
from services.prediction.mtf_factor_analyzer import MTF_WEIGHT
from services.prediction.technical_factor_analyzer import (
    EMA_WEIGHT,
    IB_WEIGHT,
    MACD_WEIGHT,
    RSI_WEIGHT,
    RVOL_WEIGHT,
    SUPERTREND_WEIGHT,
    VWAP_WEIGHT,
)
from services.prediction.vix_factor_analyzer import VIX_WEIGHT
from services.premarket.prediction_bridge import PREMARKET_WEIGHT

# Nominal intended ACTIVE weights at full availability (DTE=0 max-pain, no decay).
# Disabled-by-design factors (ΔOI, IV Rank) are intentionally excluded from the budget.
# Do not retune these numbers to chase coverage or signal_score targets.


class PredictionWeightBudget:
    """Coverage = sum(active weights) / intended_budget. Score still renorms over active weights only."""

    def __init__(self, agent_weight: float):
        if not 0.10 <= agent_weight <= 0.15:
            raise ValueError("agent_weight for budget must stay in [0.10, 0.15]")
        self._agent_weight = agent_weight
        self._intended = round(
            agent_weight
            + PCR_WEIGHT
            + MAX_PAIN_WEIGHT
            + OI_WALL_WEIGHT
            + EMA_WEIGHT
            + RSI_WEIGHT
            + MACD_WEIGHT
            + SUPERTREND_WEIGHT
            + VWAP_WEIGHT
            + RVOL_WEIGHT
            + IB_WEIGHT
            + PREMARKET_WEIGHT
            + VIX_WEIGHT
            + BREADTH_WEIGHT
            + MTF_WEIGHT,
            4,
        )

    @property
    def intended_total(self) -> float:
        return self._intended

    def coverage(self, factors: List[PredictionFactor]) -> float:
        active_weight = sum(
            f.weight for f in factors if f.status == FactorStatus.ACTIVE and f.weight > 0
        )
        if self._intended <= 0:
            return 0.0
        return round(min(1.0, active_weight / self._intended), 3)
