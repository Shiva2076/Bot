from typing import List

from schemas.prediction import ChartDataQuality
from schemas.trading import Candle
from services.prediction.chart_candle_policy import ChartCandlePolicy


class ChartCandleValidator:
    """Validates ordering, duplicates, and intraday gaps on completed candles."""

    def __init__(self, policy: ChartCandlePolicy):
        self._policy = policy

    def validate(self, candles: List[Candle], interval_minutes: int) -> ChartDataQuality:
        if not candles:
            return ChartDataQuality(
                ok=False, ordered=True, duplicate_bars=0, gap_count=0, detail="no candles"
            )
        times = [c.time for c in candles]
        ordered = all(times[i] < times[i + 1] for i in range(len(times) - 1))
        duplicates = len(times) - len(set(times))
        expected = interval_minutes * 60
        gaps = 0
        for i in range(1, len(candles)):
            delta = candles[i].time - candles[i - 1].time
            same_session = self._policy.session_date(candles[i]) == self._policy.session_date(
                candles[i - 1]
            )
            if same_session and delta > expected * 1.5:
                gaps += 1
        ok = ordered and duplicates == 0
        detail = "ok" if ok else "candle series has ordering or duplicate issues"
        if gaps > 0:
            detail = f"{detail}; {gaps} intraday gap(s)"
        return ChartDataQuality(
            ok=ok, ordered=ordered, duplicate_bars=duplicates, gap_count=gaps, detail=detail
        )
