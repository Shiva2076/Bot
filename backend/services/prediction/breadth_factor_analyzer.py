"""
Breadth Factor Analyzer — converts live NSE advance/decline data into a
PredictionFactor that filters false index signals.

A Nifty CALL signal is more reliable when most stocks are advancing;
if the index is rising on deteriorating breadth, the signal is suspect.
"""
from schemas.prediction import FactorCluster, PredictionFactor
from schemas.premarket import BreadthSnapshot
from services.prediction.factor_builder import PredictionFactorBuilder

BREADTH_WEIGHT = 0.05

# A/D ratio thresholds
STRONG_BULLISH_RATIO = 1.5    # 3:2 advancing
STRONG_BEARISH_RATIO = 0.67   # 2:3 advancing


class BreadthFactorAnalyzer:
    def __init__(self, builder: PredictionFactorBuilder):
        self._builder = builder

    def analyze(self, breadth: BreadthSnapshot) -> PredictionFactor:
        if not breadth.available or breadth.advance_decline_ratio == 0:
            return self._builder.unavailable(
                name="Market Breadth (A/D)",
                detail="Live breadth data unavailable",
                cluster=FactorCluster.CONTEXT,
            )

        ratio = breadth.advance_decline_ratio
        advancing = breadth.advancing
        declining = breadth.declining
        total = advancing + declining + breadth.unchanged

        # Map ratio → score using the same logic as PremarketFactorAnalyzer._breadth()
        # so they're consistent, but this uses LIVE intraday data not premarket.
        if ratio >= STRONG_BULLISH_RATIO:
            score = 1.0
        elif ratio <= STRONG_BEARISH_RATIO:
            score = -1.0
        else:
            score = (ratio - 1.0) / 0.5

        pct_adv = round(advancing / total * 100, 0) if total else 0
        detail = (
            f"Live A/D {advancing}/{declining} (ratio {ratio:.2f}, "
            f"{pct_adv:.0f}% advancing) — "
            + (
                "broad participation confirms index move"
                if score > 0.2
                else "broad selling undermines index strength"
                if score < -0.2
                else "mixed breadth — treat index signal with caution"
            )
        )
        return self._builder.build(
            name="Market Breadth (A/D)",
            score=score,
            weight=BREADTH_WEIGHT,
            detail=detail,
            cluster=FactorCluster.CONTEXT,
        )
