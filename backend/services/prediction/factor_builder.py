import math

from schemas.prediction import FactorBias, FactorCluster, FactorStatus, PredictionFactor
from services.trading.errors import MarketDataUnavailableError

NEUTRAL_BAND = 0.1


class PredictionFactorBuilder:
    def build(self, name: str, score: float, weight: float, detail: str, cluster: FactorCluster) -> PredictionFactor:
        clamped = self._clamp(name, score)
        return PredictionFactor(
            name=name,
            bias=self._bias(clamped),
            score=clamped,
            weight=weight,
            detail=detail,
            cluster=cluster,
            status=FactorStatus.ACTIVE,
        )

    def disabled(self, name: str, score: float, detail: str, cluster: FactorCluster) -> PredictionFactor:
        clamped = self._clamp(name, score)
        return PredictionFactor(
            name=name,
            bias=self._bias(clamped),
            score=clamped,
            weight=0.0,
            detail=f"{detail} [disabled: weight 0 until fixed]",
            cluster=cluster,
            status=FactorStatus.DISABLED,
        )

    def unavailable(self, name: str, detail: str, cluster: FactorCluster) -> PredictionFactor:
        return PredictionFactor(
            name=name,
            bias=FactorBias.NEUTRAL,
            score=0.0,
            weight=0.0,
            detail=f"{detail} [unavailable: weight 0]",
            cluster=cluster,
            status=FactorStatus.UNAVAILABLE,
        )

    @staticmethod
    def _clamp(name: str, score: float) -> float:
        if math.isnan(score):
            raise MarketDataUnavailableError(f"Factor '{name}' produced a NaN score")
        return round(max(-1.0, min(1.0, score)), 2)

    @staticmethod
    def _bias(score: float) -> FactorBias:
        if score > NEUTRAL_BAND:
            return FactorBias.BULLISH
        if score < -NEUTRAL_BAND:
            return FactorBias.BEARISH
        return FactorBias.NEUTRAL
