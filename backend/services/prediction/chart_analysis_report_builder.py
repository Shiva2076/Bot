from datetime import datetime
from typing import List, Optional

from schemas.prediction import (
    ChartAnalysisReport,
    ChartDataQuality,
    ChartPatternHit,
    ChartPatternStatus,
    ChartScenario,
    ChartSetup,
    StructureBias,
)


class ChartAnalysisReportBuilder:
    def build(
        self,
        as_of: datetime,
        structure_5m: StructureBias,
        structure_15m: StructureBias,
        setup: ChartSetup,
        bias: StructureBias,
        action_hint: str,
        evidence: List[str],
        trigger: Optional[str],
        invalidation_price: Optional[float],
        invalidation_rule: Optional[str],
        patterns: List[ChartPatternHit],
        supports: List[float],
        resistances: List[float],
        data_quality: ChartDataQuality,
    ) -> ChartAnalysisReport:
        primary = patterns[0] if patterns else None
        pattern_status = primary.status if primary else ChartPatternStatus.NONE
        primary_name = primary.pattern if primary else None
        bullish = ChartScenario(
            side="BULLISH",
            summary="Bullish continuation if price holds support and reclaim/break higher structure",
            confirmation=trigger if bias == StructureBias.BULLISH else "Close above nearest resistance with structure support",
            invalidation=invalidation_rule if bias == StructureBias.BULLISH else "Close below nearest confirmed support",
            invalidation_price=invalidation_price if bias == StructureBias.BULLISH else (supports[-1] if supports else None),
        )
        bearish = ChartScenario(
            side="BEARISH",
            summary="Bearish continuation if price rejects resistance and breaks lower structure",
            confirmation=trigger if bias == StructureBias.BEARISH else "Close below nearest support with structure resistance",
            invalidation=invalidation_rule if bias == StructureBias.BEARISH else "Close above nearest confirmed resistance",
            invalidation_price=invalidation_price if bias == StructureBias.BEARISH else (resistances[0] if resistances else None),
        )
        wait = ChartScenario(
            side="WAIT",
            summary="Wait when pattern is potential/uncertain or multi-timeframe context conflicts",
            confirmation="Require confirmed break/retest or CHoCH before acting",
            invalidation=None,
            invalidation_price=None,
        )
        if action_hint == "WAIT" or pattern_status in {
            ChartPatternStatus.POTENTIAL,
            ChartPatternStatus.UNCERTAIN,
            ChartPatternStatus.NONE,
        }:
            wait = ChartScenario(
                side="WAIT",
                summary=f"WAIT preferred: setup={setup.value}, action_hint={action_hint}",
                confirmation=trigger or "Await confirmation close",
                invalidation=invalidation_rule,
                invalidation_price=invalidation_price,
            )
        detail = (
            f"5m={structure_5m.value} 15m={structure_15m.value} bias={bias.value} "
            f"setup={setup.value} pattern={primary_name or 'NONE'}"
        )
        return ChartAnalysisReport(
            structure=structure_5m,
            pattern_status=pattern_status,
            primary_pattern=primary_name,
            evidence=evidence,
            bullish=bullish,
            bearish=bearish,
            wait=wait,
            key_supports=supports,
            key_resistances=resistances,
            data_quality=data_quality,
            as_of=as_of,
            narrative=None,
            probability=None,
            detail=detail,
        )
