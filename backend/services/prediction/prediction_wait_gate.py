from typing import Dict, List, Optional

from schemas.prediction import (
    ClusterScore,
    FactorCluster,
    GateReason,
    IntradayIndicators,
    PredictionFactor,
)
from schemas.premarket import RecommendedAction
from services.prediction.prediction_weight_budget import PredictionWeightBudget

EVIDENCE_CLUSTERS = (FactorCluster.TREND, FactorCluster.LEVELS, FactorCluster.OPTIONS)


class PredictionWaitGate:
    """Hard WAIT rules. First matching reason wins; never falls back to a directional trade."""

    def __init__(
        self,
        min_coverage: float,
        weight_budget: PredictionWeightBudget,
        cluster_disagreement_epsilon: float,
        min_signal_score: float,
    ):
        self._min_coverage = min_coverage
        self._weight_budget = weight_budget
        self._cluster_epsilon = cluster_disagreement_epsilon
        self._min_signal_score = min_signal_score

    def coverage(self, factors: List[PredictionFactor]) -> float:
        return self._weight_budget.coverage(factors)

    def mtf_conflict(
        self, indicators_5m: IntradayIndicators, indicators_15m: Optional[IntradayIndicators]
    ) -> bool:
        if indicators_15m is None:
            return False
        above_5m = indicators_5m.price >= indicators_5m.ema_20
        above_15m = indicators_15m.price >= indicators_15m.ema_20
        return above_5m != above_15m

    def cluster_disagreement(self, cluster_scores: Dict[FactorCluster, ClusterScore]) -> bool:
        signed = []
        for cluster in EVIDENCE_CLUSTERS:
            score = cluster_scores[cluster].score
            if score is None or abs(score) < self._cluster_epsilon:
                continue
            signed.append(1 if score > 0 else -1)
        return len(set(signed)) > 1

    def evaluate(
        self,
        factors: List[PredictionFactor],
        cluster_scores: Dict[FactorCluster, ClusterScore],
        indicators_5m: IntradayIndicators,
        indicators_15m: Optional[IntradayIndicators],
        premarket_action: RecommendedAction,
        signal_score: float,
        invalid_data: bool,
    ) -> GateReason:
        if invalid_data:
            return GateReason.INVALID_DATA
        if premarket_action == RecommendedAction.WAIT:
            return GateReason.PREMARKET_WAIT
        if self.mtf_conflict(indicators_5m, indicators_15m):
            return GateReason.MTF_CONFLICT
        if self.cluster_disagreement(cluster_scores):
            return GateReason.CLUSTER_DISAGREEMENT
        if self.coverage(factors) < self._min_coverage:
            return GateReason.LOW_COVERAGE
        if signal_score < self._min_signal_score:
            return GateReason.LOW_SIGNAL_SCORE
        return GateReason.NONE
