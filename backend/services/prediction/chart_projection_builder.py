from typing import List, Optional

from schemas.prediction import ChartPatternStatus, ChartProjection, ChartProjectionKind
from schemas.trading import Candle
from services.prediction.chart_breakout_detector import BreakoutKind, BreakoutResult
from services.prediction.chart_double_pattern_detector import DoublePatternKind, DoublePatternResult
from services.prediction.chart_trendline_detector import ParallelChannel

EXTEND_BARS = 24
BAR_SECONDS_5M = 300


class ChartProjectionBuilder:
    """Builds rule-based forward paths from confirmed structure. Scenario only."""

    def build(
        self,
        candles: List[Candle],
        atr: float,
        channel: Optional[ParallelChannel],
        double_pattern: Optional[DoublePatternResult],
        breakout: BreakoutResult,
    ) -> List[ChartProjection]:
        if not candles or atr <= 0:
            return []
        last = candles[-1]
        projections: List[ChartProjection] = []
        projections.extend(self._channel(channel, last.time))
        projections.extend(self._double_pattern(double_pattern, last, atr))
        projections.extend(self._breakout(breakout, last, atr))
        return projections

    def _channel(self, channel: Optional[ParallelChannel], last_time: int) -> List[ChartProjection]:
        if channel is None:
            return []
        end_time = last_time + EXTEND_BARS * BAR_SECONDS_5M
        upper_end = round(channel.upper.price_end + channel.upper.slope_per_bar * EXTEND_BARS, 2)
        lower_end = round(channel.lower.price_end + channel.lower.slope_per_bar * EXTEND_BARS, 2)
        return [
            ChartProjection(
                kind=ChartProjectionKind.CHANNEL_UPPER,
                time_start=channel.upper.time_start,
                time_end=end_time,
                price_start=channel.upper.price_start,
                price_end=upper_end,
                label="Channel upper (scenario)",
                side="NEUTRAL",
                status=ChartPatternStatus.POTENTIAL,
                evidence=channel.evidence,
            ),
            ChartProjection(
                kind=ChartProjectionKind.CHANNEL_LOWER,
                time_start=channel.lower.time_start,
                time_end=end_time,
                price_start=channel.lower.price_start,
                price_end=lower_end,
                label="Channel lower (scenario)",
                side="NEUTRAL",
                status=ChartPatternStatus.POTENTIAL,
                evidence=channel.evidence,
            ),
            ChartProjection(
                kind=ChartProjectionKind.TARGET_ZONE,
                time_start=last_time,
                time_end=end_time,
                price_start=lower_end,
                price_end=upper_end,
                price_low=min(lower_end, upper_end),
                price_high=max(lower_end, upper_end),
                label="Channel path zone",
                side="NEUTRAL",
                status=ChartPatternStatus.POTENTIAL,
                evidence="Price may travel inside extended parallel channel if boundaries hold",
            ),
        ]

    def _double_pattern(
        self, pattern: Optional[DoublePatternResult], last: Candle, atr: float
    ) -> List[ChartProjection]:
        if pattern is None or pattern.status == ChartPatternStatus.FAILED:
            return []
        height = abs(pattern.neckline - pattern.peak_or_trough)
        if height <= 0:
            return []
        bullish = pattern.kind == DoublePatternKind.DOUBLE_BOTTOM
        target = (
            round(pattern.neckline + height, 2)
            if bullish
            else round(pattern.neckline - height, 2)
        )
        end_time = last.time + EXTEND_BARS * BAR_SECONDS_5M
        band = max(atr * 0.25, 5.0)
        status = pattern.status
        side = "BULLISH" if bullish else "BEARISH"
        label = "Double bottom target" if bullish else "Double top target"
        return [
            ChartProjection(
                kind=ChartProjectionKind.PATTERN_LABEL,
                time_start=pattern.time,
                time_end=pattern.time,
                price_start=pattern.peak_or_trough,
                price_end=pattern.peak_or_trough,
                label=pattern.kind.value.replace("_", " "),
                side=side,
                status=status,
                evidence=pattern.evidence,
            ),
            ChartProjection(
                kind=ChartProjectionKind.MEASURED_MOVE,
                time_start=last.time,
                time_end=end_time,
                price_start=last.close,
                price_end=target,
                label=f"{label} (scenario)",
                side=side,
                status=status,
                evidence=(
                    f"Measured move from neckline {pattern.neckline:.2f} "
                    f"using pattern height {height:.2f}"
                ),
            ),
            ChartProjection(
                kind=ChartProjectionKind.TARGET_ZONE,
                time_start=last.time,
                time_end=end_time,
                price_start=target,
                price_end=target,
                price_low=round(target - band, 2),
                price_high=round(target + band, 2),
                label="Measured target zone",
                side=side,
                status=status,
                evidence="Target zone = measured move ± 0.25 ATR; invalid if pattern invalidation hits first",
            ),
        ]

    def _breakout(self, breakout: BreakoutResult, last: Candle, atr: float) -> List[ChartProjection]:
        if breakout.kind in {BreakoutKind.NONE, BreakoutKind.FAILED_BREAK_UP, BreakoutKind.FAILED_BREAK_DOWN}:
            return []
        up = breakout.kind in {BreakoutKind.BREAK_UP, BreakoutKind.BREAK_UP_RETEST}
        move = max(atr * 1.5, 10.0)
        target = round(breakout.level + move, 2) if up else round(breakout.level - move, 2)
        end_time = last.time + EXTEND_BARS * BAR_SECONDS_5M
        status = (
            ChartPatternStatus.CONFIRMED
            if breakout.kind in {BreakoutKind.BREAK_UP_RETEST, BreakoutKind.BREAK_DOWN_RETEST}
            else ChartPatternStatus.POTENTIAL
        )
        side = "BULLISH" if up else "BEARISH"
        return [
            ChartProjection(
                kind=ChartProjectionKind.PATTERN_LABEL,
                time_start=last.time,
                time_end=last.time,
                price_start=breakout.level,
                price_end=breakout.level,
                label="BreakOut" if up else "BreakDown",
                side=side,
                status=status,
                evidence=breakout.evidence,
            ),
            ChartProjection(
                kind=ChartProjectionKind.BREAKOUT_PATH,
                time_start=last.time,
                time_end=end_time,
                price_start=last.close,
                price_end=target,
                label="Breakout path (scenario)",
                side=side,
                status=status,
                evidence=f"Rule projection: {move:.1f} pts (~1.5 ATR) beyond {breakout.level_label}",
            ),
        ]
