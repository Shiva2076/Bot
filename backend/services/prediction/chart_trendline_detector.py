from typing import List, Optional, Tuple

from pydantic import BaseModel

from schemas.trading import Candle
from services.prediction.chart_swing_detector import SwingKind, SwingPoint


class TrendlineSegment(BaseModel):
    kind: str
    price_start: float
    price_end: float
    time_start: int
    time_end: int
    slope_per_bar: float
    source: str


class ParallelChannel(BaseModel):
    upper: TrendlineSegment
    lower: TrendlineSegment
    width: float
    evidence: str


class ChartTrendlineDetector:
    """Pivot-based support/resistance trendlines and a simple parallel channel."""

    def detect(
        self, candles: List[Candle], swings: List[SwingPoint]
    ) -> Tuple[List[TrendlineSegment], Optional[ParallelChannel]]:
        highs = [s for s in swings if s.kind == SwingKind.HIGH]
        lows = [s for s in swings if s.kind == SwingKind.LOW]
        lines: List[TrendlineSegment] = []
        resistance = self._line(highs, "RESISTANCE_TRENDLINE")
        support = self._line(lows, "SUPPORT_TRENDLINE")
        if resistance is not None:
            lines.append(resistance)
        if support is not None:
            lines.append(support)
        channel = None
        if resistance is not None and support is not None:
            width = abs(
                (resistance.price_start + resistance.price_end) / 2
                - (support.price_start + support.price_end) / 2
            )
            channel = ParallelChannel(
                upper=resistance,
                lower=support,
                width=round(width, 2),
                evidence=(
                    f"Parallel channel width {width:.2f} from last two swing highs/lows"
                ),
            )
        return lines, channel

    def _line(self, pivots: List[SwingPoint], kind: str) -> Optional[TrendlineSegment]:
        if len(pivots) < 2:
            return None
        left, right = pivots[-2], pivots[-1]
        bars = right.index - left.index
        if bars <= 0:
            return None
        slope = (right.price - left.price) / bars
        return TrendlineSegment(
            kind=kind,
            price_start=round(left.price, 2),
            price_end=round(right.price, 2),
            time_start=left.time,
            time_end=right.time,
            slope_per_bar=round(slope, 4),
            source=f"pivots:{left.index}-{right.index}",
        )
