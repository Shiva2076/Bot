from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from schemas.prediction import ChartPatternStatus, StructureBias
from schemas.trading import Candle
from services.prediction.chart_swing_detector import SwingKind, SwingPoint


class DoublePatternKind(str, Enum):
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"


class DoublePatternResult(BaseModel):
    kind: DoublePatternKind
    status: ChartPatternStatus
    bias: StructureBias
    peak_or_trough: float
    neckline: float
    invalidation: float
    evidence: str
    time: int


class ChartDoublePatternDetector:
    """Double top/bottom from the last two similar swings within ATR tolerance."""

    def __init__(self, tolerance_atr: float = 0.35):
        self._tolerance_atr = tolerance_atr

    def detect(
        self, candles: List[Candle], swings: List[SwingPoint], atr: float
    ) -> Optional[DoublePatternResult]:
        if atr <= 0 or len(candles) < 8:
            return None
        tol = atr * self._tolerance_atr
        top = self._double_top(candles, swings, tol)
        bottom = self._double_bottom(candles, swings, tol)
        if top is None:
            return bottom
        if bottom is None:
            return top
        return top if top.time >= bottom.time else bottom

    def _double_top(
        self, candles: List[Candle], swings: List[SwingPoint], tol: float
    ) -> Optional[DoublePatternResult]:
        highs = [s for s in swings if s.kind == SwingKind.HIGH]
        lows = [s for s in swings if s.kind == SwingKind.LOW]
        if len(highs) < 2 or not lows:
            return None
        left, right = highs[-2], highs[-1]
        if abs(left.price - right.price) > tol:
            return None
        mid_lows = [s for s in lows if left.index < s.index < right.index]
        if not mid_lows:
            return None
        neckline = min(s.price for s in mid_lows)
        peak = max(left.price, right.price)
        after = right.confirmed_at_index + 1
        status = ChartPatternStatus.POTENTIAL
        for index in range(after, len(candles)):
            if candles[index].close < neckline:
                status = ChartPatternStatus.CONFIRMED
                break
            if candles[index].close > peak + tol:
                status = ChartPatternStatus.FAILED
                break
        return DoublePatternResult(
            kind=DoublePatternKind.DOUBLE_TOP,
            status=status,
            bias=StructureBias.BEARISH,
            peak_or_trough=round(peak, 2),
            neckline=round(neckline, 2),
            invalidation=round(peak + tol, 2),
            evidence=f"Double top near {peak:.2f}; neckline {neckline:.2f} ({status.value})",
            time=right.time,
        )

    def _double_bottom(
        self, candles: List[Candle], swings: List[SwingPoint], tol: float
    ) -> Optional[DoublePatternResult]:
        highs = [s for s in swings if s.kind == SwingKind.HIGH]
        lows = [s for s in swings if s.kind == SwingKind.LOW]
        if len(lows) < 2 or not highs:
            return None
        left, right = lows[-2], lows[-1]
        if abs(left.price - right.price) > tol:
            return None
        mid_highs = [s for s in highs if left.index < s.index < right.index]
        if not mid_highs:
            return None
        neckline = max(s.price for s in mid_highs)
        trough = min(left.price, right.price)
        after = right.confirmed_at_index + 1
        status = ChartPatternStatus.POTENTIAL
        for index in range(after, len(candles)):
            if candles[index].close > neckline:
                status = ChartPatternStatus.CONFIRMED
                break
            if candles[index].close < trough - tol:
                status = ChartPatternStatus.FAILED
                break
        return DoublePatternResult(
            kind=DoublePatternKind.DOUBLE_BOTTOM,
            status=status,
            bias=StructureBias.BULLISH,
            peak_or_trough=round(trough, 2),
            neckline=round(neckline, 2),
            invalidation=round(trough - tol, 2),
            evidence=f"Double bottom near {trough:.2f}; neckline {neckline:.2f} ({status.value})",
            time=right.time,
        )
