"""
VIX Factor Analyzer — scores India VIX as a PredictionFactor.

Rising VIX:  wider expected ranges, but also increases option premiums and
             increases risk of stop-hunting wicks → penalty for directional bets.
Falling VIX: calmer regime, trend-following and momentum signals work better.
High VIX:    option buyers pay more premium → IV-crush risk is elevated.
"""
from schemas.prediction import FactorCluster, PredictionFactor
from schemas.premarket import IndiaVixSnapshot
from services.prediction.factor_builder import PredictionFactorBuilder

VIX_WEIGHT = 0.08

# Thresholds (matching IndiaVixProvider defaults: low=12, high=20)
VIX_LOW_THRESHOLD = 12.0
VIX_HIGH_THRESHOLD = 20.0
VIX_EXTREME_THRESHOLD = 25.0   # extreme fear → heavily penalised

# VIX trend contribution (change_pct)
VIX_TREND_SCALE = 3.0          # ±3% VIX change → ±1.0 trend component


class VixFactorAnalyzer:
    def __init__(self, builder: PredictionFactorBuilder):
        self._builder = builder

    def analyze(self, vix: IndiaVixSnapshot) -> PredictionFactor:
        if not vix.available or vix.value is None:
            return self._builder.unavailable(
                name="India VIX",
                detail="India VIX quote unavailable",
                cluster=FactorCluster.REGIME,
            )

        value = vix.value
        change_pct = vix.change_pct or 0.0

        # ── Level component ──────────────────────────────────────────────────
        if value >= VIX_EXTREME_THRESHOLD:
            level_score = -1.0
        elif value >= VIX_HIGH_THRESHOLD:
            # Interpolate: high → extreme maps to -0.5 → -1.0
            level_score = -0.5 - 0.5 * (value - VIX_HIGH_THRESHOLD) / (
                VIX_EXTREME_THRESHOLD - VIX_HIGH_THRESHOLD
            )
        elif value <= VIX_LOW_THRESHOLD:
            level_score = 0.5  # calm, trend-friendly
        else:
            # Moderate zone: linearly interpolate from +0.5 to -0.5
            level_score = 0.5 - (value - VIX_LOW_THRESHOLD) / (
                VIX_HIGH_THRESHOLD - VIX_LOW_THRESHOLD
            )

        # ── Trend component ───────────────────────────────────────────────────
        # Rising VIX = expanding fear = penalise; falling = stabilising = reward
        trend_score = -(change_pct / VIX_TREND_SCALE)

        # Blend 70% level + 30% trend
        score = 0.70 * level_score + 0.30 * trend_score

        # Detail string
        band_label = vix.band.value if vix.band else "UNKNOWN"
        trend_label = vix.trend if vix.trend else "UNKNOWN"
        detail = (
            f"India VIX {value:.1f} ({band_label}) — trend {trend_label} "
            f"({change_pct:+.1f}%); "
            + (
                "extreme fear — reduce directional bets"
                if value >= VIX_EXTREME_THRESHOLD
                else "high — widen stops, option premium elevated"
                if value >= VIX_HIGH_THRESHOLD
                else "low — calm regime, trend-following favoured"
                if value <= VIX_LOW_THRESHOLD
                else "moderate — normal conditions"
            )
        )
        return self._builder.build(
            name="India VIX",
            score=score,
            weight=VIX_WEIGHT,
            detail=detail,
            cluster=FactorCluster.REGIME,
        )
