from typing import List

from schemas.prediction import PredictionDirection, PredictionFactor, FactorStatus

DIRECTION_THRESHOLD = 0.15


class PredictionScorer:
    def score(self, factors: List[PredictionFactor]) -> float:
        active = [f for f in factors if f.status == FactorStatus.ACTIVE and f.weight > 0]
        total_weight = sum(f.weight for f in active)
        if total_weight <= 0:
            return 0.0
        return round(sum(f.score * f.weight for f in active) / total_weight, 3)

    def direction(self, score: float) -> PredictionDirection:
        if score >= DIRECTION_THRESHOLD:
            return PredictionDirection.CALL
        if score <= -DIRECTION_THRESHOLD:
            return PredictionDirection.PUT
        return PredictionDirection.NO_TRADE

    def signal_score(self, score: float, time_modifier: float) -> float:
        """Uncalibrated heuristic 0–95. Not a probability of trade success."""
        raw = 50.0 + 50.0 * abs(score)
        return round(min(95.0, raw * time_modifier), 1)

    def confidence(self, score: float) -> float:
        return self.signal_score(score, 1.0)
