from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from schemas.trading import Candle


class SweepSide(str, Enum):
    NONE = "NONE"
    BEARISH = "BEARISH"
    BULLISH = "BULLISH"


class LiquiditySweepResult(BaseModel):
    side: SweepSide
    level: float
    level_label: str
    candle_index: Optional[int]
    evidence: str


class ChartLiquiditySweepDetector:
    """Wick rejection beyond a level with body/wick ratio and minimum wick noise floor."""

    def __init__(
        self,
        wick_body_ratio: float = 2.0,
        min_wick_atr_fraction: float = 0.25,
        min_wick_points: float = 8.0,
    ):
        self._wick_body_ratio = wick_body_ratio
        self._min_wick_atr_fraction = min_wick_atr_fraction
        self._min_wick_points = min_wick_points

    def detect(
        self,
        candles: List[Candle],
        resistance: Optional[float],
        support: Optional[float],
        atr: float,
        resistance_label: str,
        support_label: str,
    ) -> LiquiditySweepResult:
        if not candles or atr <= 0:
            return LiquiditySweepResult(side=SweepSide.NONE, level=0.0, level_label="", candle_index=None, evidence="")
        min_wick = max(atr * self._min_wick_atr_fraction, self._min_wick_points)
        lookback = candles[-8:]
        start_index = len(candles) - len(lookback)
        for offset, candle in enumerate(reversed(lookback)):
            index = start_index + len(lookback) - 1 - offset
            body = abs(candle.close - candle.open)
            upper = candle.high - max(candle.open, candle.close)
            lower = min(candle.open, candle.close) - candle.low
            if resistance is not None and candle.high > resistance and candle.close < resistance:
                if upper >= self._wick_body_ratio * max(body, 1e-9) and upper >= min_wick:
                    return LiquiditySweepResult(
                        side=SweepSide.BEARISH,
                        level=resistance,
                        level_label=resistance_label,
                        candle_index=index,
                        evidence=(
                            f"Bearish liquidity sweep above {resistance_label} {resistance:.2f} "
                            f"(wick {upper:.2f} >= {min_wick:.2f})"
                        ),
                    )
            if support is not None and candle.low < support and candle.close > support:
                if lower >= self._wick_body_ratio * max(body, 1e-9) and lower >= min_wick:
                    return LiquiditySweepResult(
                        side=SweepSide.BULLISH,
                        level=support,
                        level_label=support_label,
                        candle_index=index,
                        evidence=(
                            f"Bullish liquidity sweep below {support_label} {support:.2f} "
                            f"(wick {lower:.2f} >= {min_wick:.2f})"
                        ),
                    )
        return LiquiditySweepResult(side=SweepSide.NONE, level=0.0, level_label="", candle_index=None, evidence="")
