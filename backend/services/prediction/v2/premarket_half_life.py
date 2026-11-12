from datetime import datetime, time
from typing import Optional

import pytz

from schemas.prediction import FactorCluster, FactorStatus, PredictionFactor
from schemas.premarket import RecommendedAction
from services.prediction.factor_builder import PredictionFactorBuilder

IST = pytz.timezone("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
PREMARKET_V2_NAME = "Pre-Market Bias (half-life)"
_ZERO_ACTIONS = {RecommendedAction.WAIT.value, RecommendedAction.NO_TRADE.value}


class PremarketHalfLifeAnalyzer:
    """v2 pre-market bias: weight halves every `half_life_minutes` after 09:15 IST.

    Weight (not just score) is zero when the pre-market report's own action is WAIT or
    NO_TRADE, so the factor cannot dilute the other votes. v1 kept a zero score at full weight.
    """

    def __init__(self, builder: PredictionFactorBuilder, base_weight: float, half_life_minutes: float):
        if half_life_minutes <= 0:
            raise ValueError("half_life_minutes must be positive")
        self._builder = builder
        self._base_weight = base_weight
        self._half_life = half_life_minutes

    def decay(self, now: datetime) -> float:
        local = now.astimezone(IST) if now.tzinfo else IST.localize(now)
        open_at = IST.localize(datetime.combine(local.date(), SESSION_OPEN))
        minutes = (local - open_at).total_seconds() / 60.0
        if minutes <= 0:
            return 1.0
        return 0.5 ** (minutes / self._half_life)

    def analyze(
        self, live_factor: Optional[PredictionFactor], action: Optional[str], now: datetime
    ) -> PredictionFactor:
        if live_factor is None or live_factor.status == FactorStatus.UNAVAILABLE:
            return self._builder.unavailable(
                name=PREMARKET_V2_NAME, detail="Pre-market report unavailable", cluster=FactorCluster.CONTEXT
            )
        if action in _ZERO_ACTIONS:
            return self._builder.neutral(
                name=PREMARKET_V2_NAME,
                detail=f"Pre-market action {action}: zero weight (v2 rule)",
                cluster=FactorCluster.CONTEXT,
            )
        decay = self.decay(now)
        return self._builder.build(
            name=PREMARKET_V2_NAME,
            score=live_factor.score,
            weight=round(self._base_weight * decay, 4),
            detail=f"Pre-market score {live_factor.score:+.2f}; half-life {self._half_life:.0f}m → decay {decay:.2f}",
            cluster=FactorCluster.CONTEXT,
        )
