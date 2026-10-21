from typing import List, Literal, Optional, Tuple

from schemas.prediction import (
    ChartLevel,
    ChartLevelKind,
    ChartPatternHit,
    ChartPatternStatus,
    ChartSetup,
    ChartStructureFeatures,
    StructureBias,
)
from services.prediction.chart_analysis_report_builder import ChartAnalysisReportBuilder
from services.prediction.chart_annotation_builder import ChartAnnotationBuilder
from services.prediction.chart_breakout_detector import BreakoutKind, ChartBreakoutDetector
from services.prediction.chart_candle_validator import ChartCandleValidator
from services.prediction.chart_double_pattern_detector import ChartDoublePatternDetector
from services.prediction.chart_extractor_input import ChartExtractorInput
from services.prediction.chart_fvg_detector import ChartFvgDetector, FairValueGap, FvgSide
from services.prediction.chart_level_builder import ChartLevelBuilder
from services.prediction.chart_liquidity_sweep_detector import ChartLiquiditySweepDetector, SweepSide
from services.prediction.chart_projection_builder import ChartProjectionBuilder
from services.prediction.chart_structure_classifier import ChartStructureClassifier
from services.prediction.chart_structure_event_detector import (
    ChartStructureEventDetector,
    StructureEventKind,
)
from services.prediction.chart_swing_detector import ChartSwingDetector
from services.prediction.chart_trendline_detector import ChartTrendlineDetector

MIN_BARS_5M = 20
MIN_BARS_15M = 12
ActionHint = Literal["CALL", "PUT", "WAIT"]
RESISTANCE_KINDS = {
    ChartLevelKind.SESSION_HIGH,
    ChartLevelKind.PDH,
    ChartLevelKind.SWING_HIGH,
    ChartLevelKind.NECKLINE,
}
SUPPORT_KINDS = {
    ChartLevelKind.SESSION_LOW,
    ChartLevelKind.PDL,
    ChartLevelKind.SWING_LOW,
    ChartLevelKind.NECKLINE,
}


class ChartStructureExtractor:
    def __init__(
        self,
        swings: ChartSwingDetector,
        structure: ChartStructureClassifier,
        levels: ChartLevelBuilder,
        breakouts: ChartBreakoutDetector,
        sweeps: ChartLiquiditySweepDetector,
        fvgs: ChartFvgDetector,
        validator: ChartCandleValidator,
        structure_events: ChartStructureEventDetector,
        doubles: ChartDoublePatternDetector,
        trendlines: ChartTrendlineDetector,
        annotations: ChartAnnotationBuilder,
        reports: ChartAnalysisReportBuilder,
        projections: ChartProjectionBuilder,
    ):
        self._swings = swings
        self._structure = structure
        self._levels = levels
        self._breakouts = breakouts
        self._sweeps = sweeps
        self._fvgs = fvgs
        self._validator = validator
        self._structure_events = structure_events
        self._doubles = doubles
        self._trendlines = trendlines
        self._annotations = annotations
        self._reports = reports
        self._projections = projections

    def extract(self, payload: ChartExtractorInput) -> ChartStructureFeatures:
        quality = self._validator.validate(payload.candles_5m, 5)
        if payload.atr <= 0:
            return ChartStructureFeatures.unavailable(
                "ATR must be positive for chart structure", payload.as_of
            )
        if len(payload.candles_5m) < MIN_BARS_5M:
            return ChartStructureFeatures.unavailable(
                f"Need at least {MIN_BARS_5M} completed 5m candles", payload.as_of
            )
        if not quality.ok:
            unavailable = ChartStructureFeatures.unavailable(quality.detail, payload.as_of)
            return unavailable.model_copy(update={"data_quality": quality})

        swings_5m = self._swings.detect(payload.candles_5m)
        structure_5m = self._structure.classify(swings_5m)
        structure_15m = StructureBias.UNKNOWN
        if len(payload.candles_15m) >= MIN_BARS_15M:
            structure_15m = self._structure.classify(self._swings.detect(payload.candles_15m))

        opening_gap = None
        if payload.prior_day is not None and payload.today_open is not None:
            opening_gap = round(payload.today_open - payload.prior_day.pdc, 2)

        key_levels = self._levels.build(
            prior_day=payload.prior_day,
            session_range=payload.session_range,
            swings=swings_5m,
            opening_gap_points=opening_gap,
            today_open=payload.today_open,
        )

        resistance, resistance_label, support, support_label = self._primary_levels(key_levels, payload)
        breakout = self._breakouts.detect(
            payload.candles_5m, resistance, support, payload.atr, resistance_label, support_label
        )
        sweep = self._sweeps.detect(
            payload.candles_5m, resistance, support, payload.atr, resistance_label, support_label
        )
        gaps = self._fvgs.detect(payload.candles_5m)
        for gap in gaps[-2:]:
            key_levels.append(
                ChartLevel(
                    kind=ChartLevelKind.FVG_TOP,
                    price=gap.top,
                    source=f"{gap.side.value}_FVG:{gap.mid_index}",
                )
            )
            key_levels.append(
                ChartLevel(
                    kind=ChartLevelKind.FVG_BOTTOM,
                    price=gap.bottom,
                    source=f"{gap.side.value}_FVG:{gap.mid_index}",
                )
            )

        structure_event = self._structure_events.detect(
            payload.candles_5m, swings_5m, structure_5m, payload.atr
        )
        double_pattern = self._doubles.detect(payload.candles_5m, swings_5m, payload.atr)
        trendlines, channel = self._trendlines.detect(payload.candles_5m, swings_5m)

        setup, bias, action, trigger, invalidation, invalidation_rule, evidence = self._resolve_setup(
            structure_5m=structure_5m,
            breakout_kind=breakout.kind,
            breakout_level=breakout.level,
            breakout_evidence=breakout.evidence,
            sweep_side=sweep.side,
            sweep_level=sweep.level,
            sweep_evidence=sweep.evidence,
            gaps=gaps,
            last_close=payload.candles_5m[-1].close,
            structure_event=structure_event,
            double_pattern=double_pattern,
            channel_evidence=channel.evidence if channel is not None else None,
        )

        if structure_event is not None:
            key_levels.append(
                ChartLevel(
                    kind=ChartLevelKind.BOS
                    if structure_event.kind == StructureEventKind.BOS
                    else ChartLevelKind.CHOCH,
                    price=structure_event.level,
                    source=structure_event.kind.value,
                )
            )
        if double_pattern is not None:
            key_levels.append(
                ChartLevel(
                    kind=ChartLevelKind.NECKLINE,
                    price=double_pattern.neckline,
                    source=double_pattern.kind.value,
                )
            )

        patterns = self._pattern_hits(structure_event, double_pattern, channel)
        annotations = self._annotations.build(
            key_levels=key_levels,
            gaps=gaps,
            trendlines=trendlines,
            channel=channel,
            structure_event=structure_event,
            double_pattern=double_pattern,
            invalidation_price=invalidation,
        )
        projections = self._projections.build(
            candles=payload.candles_5m,
            atr=payload.atr,
            channel=channel,
            double_pattern=double_pattern,
            breakout=breakout,
        )
        if projections:
            evidence = evidence + [p.evidence for p in projections if p.kind.value.endswith("PATH") or p.kind.value == "MEASURED_MOVE"]
        supports = sorted(
            {level.price for level in key_levels if level.kind in SUPPORT_KINDS}
        )
        resistances = sorted(
            {level.price for level in key_levels if level.kind in RESISTANCE_KINDS}
        )
        report = self._reports.build(
            as_of=payload.as_of,
            structure_5m=structure_5m,
            structure_15m=structure_15m,
            setup=setup,
            bias=bias,
            action_hint=action,
            evidence=evidence,
            trigger=trigger,
            invalidation_price=invalidation,
            invalidation_rule=invalidation_rule,
            patterns=patterns,
            supports=supports,
            resistances=resistances,
            data_quality=quality,
        )
        detail = (
            f"5m={structure_5m.value} 15m={structure_15m.value} setup={setup.value} "
            f"action={action}; shadow-only"
        )
        return ChartStructureFeatures(
            as_of=payload.as_of,
            interval_5m_bars=len(payload.candles_5m),
            interval_15m_bars=len(payload.candles_15m),
            structure_5m=structure_5m,
            structure_15m=structure_15m,
            setup=setup,
            bias=bias,
            action_hint=action,
            key_levels=key_levels,
            evidence=evidence,
            trigger=trigger,
            invalidation_price=invalidation,
            invalidation_rule=invalidation_rule,
            probability=None,
            opening_gap_points=opening_gap,
            data_ok=True,
            detail=detail,
            annotations=annotations,
            patterns=patterns,
            projections=projections,
            report=report,
            data_quality=quality,
        )

    def _pattern_hits(self, structure_event, double_pattern, channel) -> List[ChartPatternHit]:
        hits: List[ChartPatternHit] = []
        if structure_event is not None:
            hits.append(
                ChartPatternHit(
                    pattern=structure_event.kind.value,
                    status=ChartPatternStatus.CONFIRMED,
                    bias=structure_event.bias,
                    level=structure_event.level,
                    invalidation=structure_event.level,
                    confirmation="Close through structure level held",
                    evidence=structure_event.evidence,
                    time=structure_event.time,
                )
            )
        if double_pattern is not None:
            hits.append(
                ChartPatternHit(
                    pattern=double_pattern.kind.value,
                    status=double_pattern.status,
                    bias=double_pattern.bias,
                    level=double_pattern.neckline,
                    invalidation=double_pattern.invalidation,
                    confirmation=f"Close beyond neckline {double_pattern.neckline:.2f}",
                    evidence=double_pattern.evidence,
                    time=double_pattern.time,
                )
            )
        if channel is not None:
            hits.append(
                ChartPatternHit(
                    pattern="CHANNEL",
                    status=ChartPatternStatus.POTENTIAL,
                    bias=StructureBias.RANGE,
                    level=None,
                    invalidation=None,
                    confirmation="Respect channel boundaries on retest",
                    evidence=channel.evidence,
                    time=channel.upper.time_end,
                )
            )
        return hits

    def _primary_levels(
        self, levels: List[ChartLevel], payload: ChartExtractorInput
    ) -> Tuple[Optional[float], str, Optional[float], str]:
        last = payload.candles_5m[-1].close
        above = [level for level in levels if level.kind in RESISTANCE_KINDS and level.price >= last]
        below = [level for level in levels if level.kind in SUPPORT_KINDS and level.price <= last]
        if above:
            nearest = min(above, key=lambda level: level.price)
            resistance, resistance_label = nearest.price, nearest.kind.value
        else:
            fallback_r = [level for level in levels if level.kind in RESISTANCE_KINDS]
            resistance = fallback_r[0].price if fallback_r else None
            resistance_label = fallback_r[0].kind.value if fallback_r else "resistance"
        if below:
            nearest_s = max(below, key=lambda level: level.price)
            support, support_label = nearest_s.price, nearest_s.kind.value
        else:
            fallback_s = [level for level in levels if level.kind in SUPPORT_KINDS]
            support = fallback_s[0].price if fallback_s else None
            support_label = fallback_s[0].kind.value if fallback_s else "support"
        return resistance, resistance_label, support, support_label

    def _resolve_setup(
        self,
        structure_5m: StructureBias,
        breakout_kind: BreakoutKind,
        breakout_level: float,
        breakout_evidence: str,
        sweep_side: SweepSide,
        sweep_level: float,
        sweep_evidence: str,
        gaps: List[FairValueGap],
        last_close: float,
        structure_event,
        double_pattern,
        channel_evidence: Optional[str],
    ) -> Tuple[
        ChartSetup,
        StructureBias,
        ActionHint,
        Optional[str],
        Optional[float],
        Optional[str],
        List[str],
    ]:
        evidence: List[str] = [f"5m structure {structure_5m.value}"]
        if structure_event is not None and structure_event.kind == StructureEventKind.CHOCH:
            evidence.append(structure_event.evidence)
            return (
                ChartSetup.CHANGE_OF_CHARACTER,
                structure_event.bias,
                "WAIT",
                "Hold beyond CHoCH level on retest",
                structure_event.level,
                "5m close back through CHoCH level",
                evidence,
            )
        if double_pattern is not None and double_pattern.status != ChartPatternStatus.FAILED:
            evidence.append(double_pattern.evidence)
            action: ActionHint = "WAIT"
            if double_pattern.status == ChartPatternStatus.CONFIRMED:
                action = "PUT" if double_pattern.bias == StructureBias.BEARISH else "CALL"
            setup = (
                ChartSetup.DOUBLE_TOP
                if double_pattern.kind.value == "DOUBLE_TOP"
                else ChartSetup.DOUBLE_BOTTOM
            )
            return (
                setup,
                double_pattern.bias,
                action,
                f"Respect neckline {double_pattern.neckline:.2f}",
                double_pattern.invalidation,
                f"Close beyond invalidation {double_pattern.invalidation:.2f}",
                evidence,
            )
        if structure_event is not None and structure_event.kind == StructureEventKind.BOS:
            evidence.append(structure_event.evidence)
            return (
                ChartSetup.BREAK_OF_STRUCTURE,
                structure_event.bias,
                "WAIT",
                "Retest of BOS level holds",
                structure_event.level,
                "5m close back through BOS level",
                evidence,
            )
        if sweep_side == SweepSide.BEARISH:
            evidence.append(sweep_evidence)
            return (
                ChartSetup.LIQUIDITY_SWEEP_REVERSAL,
                StructureBias.BEARISH,
                "WAIT",
                "Confirmation close below sweep midpoint",
                sweep_level,
                "5m close back above swept resistance",
                evidence,
            )
        if sweep_side == SweepSide.BULLISH:
            evidence.append(sweep_evidence)
            return (
                ChartSetup.LIQUIDITY_SWEEP_REVERSAL,
                StructureBias.BULLISH,
                "WAIT",
                "Confirmation close above sweep midpoint",
                sweep_level,
                "5m close back below swept support",
                evidence,
            )
        if breakout_kind == BreakoutKind.BREAK_DOWN_RETEST:
            evidence.append(breakout_evidence)
            return (
                ChartSetup.SUPPORT_BREAKDOWN_RETEST,
                StructureBias.BEARISH,
                "PUT",
                "Retest rejects broken support",
                breakout_level,
                "5m close back above broken support",
                evidence,
            )
        if breakout_kind == BreakoutKind.BREAK_UP_RETEST:
            evidence.append(breakout_evidence)
            return (
                ChartSetup.RESISTANCE_BREAKOUT_RETEST,
                StructureBias.BULLISH,
                "CALL",
                "Retest holds broken resistance",
                breakout_level,
                "5m close back below broken resistance",
                evidence,
            )
        if breakout_kind in {BreakoutKind.BREAK_DOWN, BreakoutKind.BREAK_UP}:
            evidence.append(breakout_evidence)
            bias = StructureBias.BEARISH if breakout_kind == BreakoutKind.BREAK_DOWN else StructureBias.BULLISH
            return (
                ChartSetup.SUPPORT_BREAKDOWN_RETEST
                if breakout_kind == BreakoutKind.BREAK_DOWN
                else ChartSetup.RESISTANCE_BREAKOUT_RETEST,
                bias,
                "WAIT",
                "Await retest confirmation",
                breakout_level,
                "5m close reclaims break level",
                evidence,
            )
        unfilled = [g for g in gaps if not g.filled]
        if unfilled:
            gap = unfilled[-1]
            evidence.append(f"Unfilled {gap.side.value} FVG {gap.bottom:.2f}-{gap.top:.2f}")
            in_zone = gap.bottom <= last_close <= gap.top
            bias = StructureBias.BULLISH if gap.side == FvgSide.BULLISH else StructureBias.BEARISH
            return (
                ChartSetup.FVG_RETEST,
                bias,
                "WAIT" if not in_zone else ("CALL" if bias == StructureBias.BULLISH else "PUT"),
                "Price reacts inside unfilled FVG",
                gap.top if gap.side == FvgSide.BEARISH else gap.bottom,
                "5m close through opposite side of FVG",
                evidence,
            )
        if channel_evidence is not None and structure_5m == StructureBias.RANGE:
            evidence.append(channel_evidence)
            return (
                ChartSetup.CHANNEL,
                StructureBias.RANGE,
                "WAIT",
                "Wait for channel break and retest",
                None,
                None,
                evidence,
            )
        if structure_5m == StructureBias.RANGE:
            evidence.append("No confirmed break/retest or sweep")
            return (
                ChartSetup.RANGE_COMPRESSION,
                StructureBias.RANGE,
                "WAIT",
                None,
                None,
                None,
                evidence,
            )
        evidence.append("Structure bias only; no confirmed trigger")
        return (
            ChartSetup.NONE,
            structure_5m,
            "WAIT",
            None,
            None,
            None,
            evidence,
        )
