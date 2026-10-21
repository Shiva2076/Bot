from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from schemas.trading import Candle


class BreakoutKind(str, Enum):
    NONE = "NONE"
    BREAK_UP = "BREAK_UP"
    BREAK_DOWN = "BREAK_DOWN"
    BREAK_UP_RETEST = "BREAK_UP_RETEST"
    BREAK_DOWN_RETEST = "BREAK_DOWN_RETEST"
    FAILED_BREAK_UP = "FAILED_BREAK_UP"
    FAILED_BREAK_DOWN = "FAILED_BREAK_DOWN"


class BreakoutResult(BaseModel):
    kind: BreakoutKind
    level: float
    level_label: str
    break_index: Optional[int]
    evidence: str


class ChartBreakoutDetector:
    def __init__(self, epsilon_atr_fraction: float = 0.05, retest_tolerance_atr: float = 0.15, retest_bars: int = 6):
        self._epsilon_atr_fraction = epsilon_atr_fraction
        self._retest_tolerance_atr = retest_tolerance_atr
        self._retest_bars = retest_bars

    def detect(
        self,
        candles: List[Candle],
        resistance: Optional[float],
        support: Optional[float],
        atr: float,
        resistance_label: str,
        support_label: str,
    ) -> BreakoutResult:
        if atr <= 0 or not candles:
            return BreakoutResult(kind=BreakoutKind.NONE, level=0.0, level_label="", break_index=None, evidence="")
        epsilon = atr * self._epsilon_atr_fraction
        tolerance = atr * self._retest_tolerance_atr
        up = self._scan_break(candles, resistance, epsilon, tolerance, upward=True, label=resistance_label)
        down = self._scan_break(candles, support, epsilon, tolerance, upward=False, label=support_label)
        if up.kind != BreakoutKind.NONE and down.kind != BreakoutKind.NONE:
            up_idx = up.break_index if up.break_index is not None else -1
            down_idx = down.break_index if down.break_index is not None else -1
            return up if up_idx >= down_idx else down
        if up.kind != BreakoutKind.NONE:
            return up
        return down

    def _scan_break(
        self,
        candles: List[Candle],
        level: Optional[float],
        epsilon: float,
        tolerance: float,
        upward: bool,
        label: str,
    ) -> BreakoutResult:
        if level is None:
            return BreakoutResult(kind=BreakoutKind.NONE, level=0.0, level_label=label, break_index=None, evidence="")
        break_index: Optional[int] = None
        for index, candle in enumerate(candles):
            if upward and candle.close > level + epsilon:
                break_index = index
                break
            if not upward and candle.close < level - epsilon:
                break_index = index
                break
        if break_index is None:
            return BreakoutResult(kind=BreakoutKind.NONE, level=level, level_label=label, break_index=None, evidence="")
        window = candles[break_index + 1 : break_index + 1 + self._retest_bars]
        if not window:
            kind = BreakoutKind.BREAK_UP if upward else BreakoutKind.BREAK_DOWN
            return BreakoutResult(
                kind=kind,
                level=level,
                level_label=label,
                break_index=break_index,
                evidence=f"Close beyond {label} at {level:.2f}; retest pending",
            )
        touched = False
        for candle in window:
            near = abs(candle.low - level) <= tolerance or abs(candle.high - level) <= tolerance
            if near or (upward and candle.low <= level + tolerance) or (not upward and candle.high >= level - tolerance):
                touched = True
            if upward and candle.close < level - epsilon:
                return BreakoutResult(
                    kind=BreakoutKind.FAILED_BREAK_UP,
                    level=level,
                    level_label=label,
                    break_index=break_index,
                    evidence=f"Failed breakout above {label} {level:.2f}",
                )
            if not upward and candle.close > level + epsilon:
                return BreakoutResult(
                    kind=BreakoutKind.FAILED_BREAK_DOWN,
                    level=level,
                    level_label=label,
                    break_index=break_index,
                    evidence=f"Failed breakdown below {label} {level:.2f}",
                )
        if touched:
            kind = BreakoutKind.BREAK_UP_RETEST if upward else BreakoutKind.BREAK_DOWN_RETEST
            side = "resistance" if upward else "support"
            return BreakoutResult(
                kind=kind,
                level=level,
                level_label=label,
                break_index=break_index,
                evidence=f"Break and retest of {side} {label} at {level:.2f}",
            )
        kind = BreakoutKind.BREAK_UP if upward else BreakoutKind.BREAK_DOWN
        return BreakoutResult(
            kind=kind,
            level=level,
            level_label=label,
            break_index=break_index,
            evidence=f"Close beyond {label} at {level:.2f}; no retest yet",
        )
