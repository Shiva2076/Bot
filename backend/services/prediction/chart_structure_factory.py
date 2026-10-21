from services.prediction.chart_analysis_interpreter import ChartAnalysisInterpreter
from services.prediction.chart_analysis_report_builder import ChartAnalysisReportBuilder
from services.prediction.chart_annotation_builder import ChartAnnotationBuilder
from services.prediction.chart_breakout_detector import ChartBreakoutDetector
from services.prediction.chart_candle_policy import ChartCandlePolicy
from services.prediction.chart_candle_validator import ChartCandleValidator
from services.prediction.chart_double_pattern_detector import ChartDoublePatternDetector
from services.prediction.chart_fvg_detector import ChartFvgDetector
from services.prediction.chart_level_builder import ChartLevelBuilder
from services.prediction.chart_liquidity_sweep_detector import ChartLiquiditySweepDetector
from services.prediction.chart_prior_day_levels import ChartPriorDayLevelBuilder
from services.prediction.chart_projection_builder import ChartProjectionBuilder
from services.prediction.chart_structure_classifier import ChartStructureClassifier
from services.prediction.chart_structure_extractor import ChartStructureExtractor
from services.prediction.chart_structure_mapper import ChartStructureMapper
from services.prediction.chart_structure_event_detector import ChartStructureEventDetector
from services.prediction.chart_structure_shadow_calculator import ChartStructureShadowCalculator
from services.prediction.chart_swing_detector import ChartSwingDetector
from services.prediction.chart_trendline_detector import ChartTrendlineDetector
from services.trading.failover_market_data import FailoverMarketData


class ChartStructureFactory:
    @staticmethod
    def policy() -> ChartCandlePolicy:
        return ChartCandlePolicy()

    @staticmethod
    def extractor(policy: ChartCandlePolicy) -> ChartStructureExtractor:
        return ChartStructureExtractor(
            swings=ChartSwingDetector(),
            structure=ChartStructureClassifier(),
            levels=ChartLevelBuilder(),
            breakouts=ChartBreakoutDetector(),
            sweeps=ChartLiquiditySweepDetector(),
            fvgs=ChartFvgDetector(policy),
            validator=ChartCandleValidator(policy),
            structure_events=ChartStructureEventDetector(),
            doubles=ChartDoublePatternDetector(),
            trendlines=ChartTrendlineDetector(),
            annotations=ChartAnnotationBuilder(),
            reports=ChartAnalysisReportBuilder(),
            projections=ChartProjectionBuilder(),
        )

    @staticmethod
    def shadow_calculator(
        market_data: FailoverMarketData, gemini_api_key: str
    ) -> ChartStructureShadowCalculator:
        policy = ChartStructureFactory.policy()
        return ChartStructureShadowCalculator(
            market_data=market_data,
            mapper=ChartStructureMapper(policy, ChartPriorDayLevelBuilder(policy)),
            extractor=ChartStructureFactory.extractor(policy),
            interpreter=ChartAnalysisInterpreter(gemini_api_key),
        )
