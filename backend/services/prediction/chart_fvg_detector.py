from enum import Enum
from typing import List

from pydantic import BaseModel

from schemas.trading import Candle
from services.prediction.chart_candle_policy import ChartCandlePolicy


class FvgSide(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class FairValueGap(BaseModel):
    side: FvgSide
    top: float
    bottom: float
    mid_index: int
    filled: bool


class ChartFvgDetector:
    """3-bar FVGs that must form within the same IST session date."""

    def __init__(self, policy: ChartCandlePolicy):
        self._policy = policy

    def detect(self, candles: List[Candle]) -> List[FairValueGap]:
        gaps: List[FairValueGap] = []
        if len(candles) < 3:
            return gaps
        for mid in range(1, len(candles) - 1):
            left = candles[mid - 1]
            center = candles[mid]
            right = candles[mid + 1]
            if not self._same_session(left, center, right):
                continue
            if right.low > left.high:
                top = right.low
                bottom = left.high
                gaps.append(
                    FairValueGap(
                        side=FvgSide.BULLISH,
                        top=round(top, 2),
                        bottom=round(bottom, 2),
                        mid_index=mid,
                        filled=self._filled(candles[mid + 1 :], bottom, top, bullish=True),
                    )
                )
            if right.high < left.low:
                top = left.low
                bottom = right.high
                gaps.append(
                    FairValueGap(
                        side=FvgSide.BEARISH,
                        top=round(top, 2),
                        bottom=round(bottom, 2),
                        mid_index=mid,
                        filled=self._filled(candles[mid + 1 :], bottom, top, bullish=False),
                    )
                )
        return gaps

    def _same_session(self, left: Candle, center: Candle, right: Candle) -> bool:
        return (
            self._policy.session_date(left)
            == self._policy.session_date(center)
            == self._policy.session_date(right)
        )

    @staticmethod
    def _filled(later: List[Candle], bottom: float, top: float, bullish: bool) -> bool:
        for candle in later:
            if bullish and candle.low <= bottom:
                return True
            if not bullish and candle.high >= top:
                return True
        return False
