from typing import List, Optional

from schemas.prediction import (
    ChartAnnotation,
    ChartAnnotationCategory,
    ChartLevel,
    ChartLevelKind,
    ChartPatternStatus,
)
from services.prediction.chart_double_pattern_detector import DoublePatternResult
from services.prediction.chart_fvg_detector import FairValueGap
from services.prediction.chart_structure_event_detector import StructureEvent
from services.prediction.chart_trendline_detector import ParallelChannel, TrendlineSegment


class ChartAnnotationBuilder:
    def build(
        self,
        key_levels: List[ChartLevel],
        gaps: List[FairValueGap],
        trendlines: List[TrendlineSegment],
        channel: Optional[ParallelChannel],
        structure_event: Optional[StructureEvent],
        double_pattern: Optional[DoublePatternResult],
        invalidation_price: Optional[float],
    ) -> List[ChartAnnotation]:
        annotations: List[ChartAnnotation] = []
        for level in key_levels:
            category = ChartAnnotationCategory.LEVELS
            if level.kind in {ChartLevelKind.FVG_TOP, ChartLevelKind.FVG_BOTTOM}:
                category = ChartAnnotationCategory.FVG
            annotations.append(
                ChartAnnotation(
                    category=category,
                    kind=level.kind.value,
                    price=level.price,
                    source=level.source,
                    status=ChartPatternStatus.CONFIRMED,
                    label=level.kind.value.replace("_", " "),
                )
            )
        for gap in gaps[-3:]:
            annotations.append(
                ChartAnnotation(
                    category=ChartAnnotationCategory.FVG,
                    kind=f"{gap.side.value}_FVG",
                    price_low=gap.bottom,
                    price_high=gap.top,
                    source=f"fvg:{gap.mid_index}",
                    status=ChartPatternStatus.FAILED if gap.filled else ChartPatternStatus.CONFIRMED,
                    label=f"{gap.side.value} FVG{' filled' if gap.filled else ''}",
                )
            )
        for line in trendlines:
            annotations.append(
                ChartAnnotation(
                    category=ChartAnnotationCategory.TRENDLINES,
                    kind=line.kind,
                    price=line.price_end,
                    price_low=min(line.price_start, line.price_end),
                    price_high=max(line.price_start, line.price_end),
                    time_start=line.time_start,
                    time_end=line.time_end,
                    source=line.source,
                    status=ChartPatternStatus.CONFIRMED,
                    label=line.kind.replace("_", " "),
                )
            )
        if channel is not None:
            annotations.append(
                ChartAnnotation(
                    category=ChartAnnotationCategory.ZONES,
                    kind="CHANNEL",
                    price_low=min(channel.lower.price_end, channel.upper.price_end),
                    price_high=max(channel.lower.price_end, channel.upper.price_end),
                    time_start=min(channel.lower.time_start, channel.upper.time_start),
                    time_end=max(channel.lower.time_end, channel.upper.time_end),
                    source="parallel_channel",
                    status=ChartPatternStatus.POTENTIAL,
                    label=f"Channel width {channel.width:.1f}",
                )
            )
        if structure_event is not None:
            annotations.append(
                ChartAnnotation(
                    category=ChartAnnotationCategory.PATTERNS,
                    kind=structure_event.kind.value,
                    price=structure_event.level,
                    time_start=structure_event.time,
                    time_end=structure_event.time,
                    source="structure_event",
                    status=ChartPatternStatus.CONFIRMED,
                    label=f"{structure_event.kind.value} {structure_event.bias.value}",
                )
            )
        if double_pattern is not None:
            annotations.append(
                ChartAnnotation(
                    category=ChartAnnotationCategory.PATTERNS,
                    kind=double_pattern.kind.value,
                    price=double_pattern.neckline,
                    price_low=min(double_pattern.neckline, double_pattern.peak_or_trough),
                    price_high=max(double_pattern.neckline, double_pattern.peak_or_trough),
                    time_start=double_pattern.time,
                    source="double_pattern",
                    status=double_pattern.status,
                    label=double_pattern.kind.value.replace("_", " "),
                )
            )
        if invalidation_price is not None:
            annotations.append(
                ChartAnnotation(
                    category=ChartAnnotationCategory.SCENARIOS,
                    kind="INVALIDATION",
                    price=invalidation_price,
                    source="setup_invalidation",
                    status=ChartPatternStatus.CONFIRMED,
                    label="Invalidation",
                )
            )
        return annotations
