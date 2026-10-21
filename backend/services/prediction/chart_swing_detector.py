from enum import Enum
from typing import List

from pydantic import BaseModel

from schemas.trading import Candle


class SwingKind(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class SwingPoint(BaseModel):
    index: int
    price: float
    kind: SwingKind
    confirmed_at_index: int
    time: int


class ChartSwingDetector:
    """Confirmed pivot highs/lows with left/right bars; no lookahead before confirmation."""

    def __init__(self, left: int = 2, right: int = 2):
        if left < 1 or right < 1:
            raise ValueError("swing left/right must be >= 1")
        self._left = left
        self._right = right

    def detect(self, candles: List[Candle]) -> List[SwingPoint]:
        points: List[SwingPoint] = []
        last_confirmable = len(candles) - self._right - 1
        for index in range(self._left, last_confirmable + 1):
            pivot = candles[index]
            left = candles[index - self._left : index]
            right = candles[index + 1 : index + self._right + 1]
            if all(pivot.high > c.high for c in left) and all(pivot.high > c.high for c in right):
                points.append(
                    SwingPoint(
                        index=index,
                        price=pivot.high,
                        kind=SwingKind.HIGH,
                        confirmed_at_index=index + self._right,
                        time=pivot.time,
                    )
                )
            if all(pivot.low < c.low for c in left) and all(pivot.low < c.low for c in right):
                points.append(
                    SwingPoint(
                        index=index,
                        price=pivot.low,
                        kind=SwingKind.LOW,
                        confirmed_at_index=index + self._right,
                        time=pivot.time,
                    )
                )
        return points
