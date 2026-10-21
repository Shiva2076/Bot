"""
MTF Factor Analyzer — Multi-Timeframe EMA alignment.

A 5-min MACD crossover against a 15-min downtrend is a bad trade.
This analyzer checks whether the higher-timeframe (15m) EMA trend agrees
with the 5m signal, acting as a structural filter.
"""
from typing import Optional

from schemas.prediction import FactorCluster, IntradayIndicators, PredictionFactor
from services.prediction.factor_builder import PredictionFactorBuilder

MTF_WEIGHT = 0.08


class MTFFactorAnalyzer:
    def __init__(self, builder: PredictionFactorBuilder):
        self._builder = builder

    def analyze(
        self,
        indicators_5m: IntradayIndicators,
        indicators_15m: Optional[IntradayIndicators],
    ) -> Optional[PredictionFactor]:
        """
        Returns None if 15m data is unavailable (graceful degradation).
        Score:
          +1.0  — 5m and 15m both above their EMA 20 (aligned bullish)
          -1.0  — 5m and 15m both below their EMA 20 (aligned bearish)
           0.0  — conflict (one above, one below) → warns of chop
          intermediate — partial alignment
        """
        if indicators_15m is None:
            return None

        above_5m = indicators_5m.price >= indicators_5m.ema_20
        above_15m = indicators_15m.price >= indicators_15m.ema_20

        # Supertrend cross-validate (if available)
        st_5m = indicators_5m.supertrend_direction
        st_15m = indicators_15m.supertrend_direction

        if above_5m and above_15m and st_5m > 0 and st_15m > 0:
            score = 1.0
            detail = "5m and 15m both bullish (price above EMA20 + Supertrend up)"
        elif not above_5m and not above_15m and st_5m < 0 and st_15m < 0:
            score = -1.0
            detail = "5m and 15m both bearish (price below EMA20 + Supertrend down)"
        elif above_5m and above_15m:
            score = 0.7
            detail = "5m and 15m price both above EMA20 — bullish structure"
        elif not above_5m and not above_15m:
            score = -0.7
            detail = "5m and 15m price both below EMA20 — bearish structure"
        elif above_5m != above_15m:
            # Conflict: timeframes disagree → discount signal
            score = 0.1 if above_5m else -0.1
            direction = "5m bullish but 15m bearish" if above_5m else "5m bearish but 15m bullish"
            detail = f"MTF conflict — {direction}; treat 5m signal with caution"
        else:
            score = 0.0
            detail = "Indeterminate MTF alignment"

        return self._builder.build(
            name="MTF EMA Alignment (5m vs 15m)",
            score=score,
            weight=MTF_WEIGHT,
            detail=detail,
            cluster=FactorCluster.TREND,
        )
