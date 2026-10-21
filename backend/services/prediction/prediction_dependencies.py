from typing import Optional

from pydantic import BaseModel, ConfigDict

from services.premarket.prediction_bridge import PremarketPredictionBridge
from services.premarket.india_vix_provider import IndiaVixProvider
from services.prediction.adx_regime_multiplier import AdxRegimeMultiplier
from services.prediction.agent_consensus_provider import AgentConsensusProvider
from services.prediction.agent_factor_analyzer import AgentFactorAnalyzer
from services.prediction.breadth_factor_analyzer import BreadthFactorAnalyzer
from services.prediction.chain_factor_analyzer import ChainFactorAnalyzer
from services.prediction.chain_metrics_calculator import ChainMetricsCalculator
from services.prediction.chain_shadow_calculator import ChainShadowCalculator
from services.prediction.chart_structure_shadow_calculator import ChartStructureShadowCalculator
from services.prediction.factor_cluster_summarizer import FactorClusterSummarizer
from services.prediction.factor_contribution_annotator import FactorContributionAnnotator
from services.prediction.futures_flow_tracker import FuturesFlowTracker
from services.prediction.intraday_indicator_provider import IntradayIndicatorProvider
from services.prediction.mtf_factor_analyzer import MTFFactorAnalyzer
from services.prediction.prediction_market_gate import PredictionMarketGate
from services.prediction.prediction_wait_gate import PredictionWaitGate
from services.prediction.premium_level_planner import PremiumLevelPlanner
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.raw_regime_classifier import RawRegimeClassifier
from services.prediction.strike_selector import StrikeSelector
from services.prediction.technical_factor_analyzer import TechnicalFactorAnalyzer
from services.prediction.time_context_analyzer import TimeContextAnalyzer
from services.prediction.vix_factor_analyzer import VixFactorAnalyzer


class PredictionSources(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    agents: AgentConsensusProvider
    indicators: IntradayIndicatorProvider
    indicators_15m: Optional[IntradayIndicatorProvider] = None
    premarket: PremarketPredictionBridge
    vix: Optional[IndiaVixProvider] = None
    futures: FuturesFlowTracker


class PredictionAnalyzers(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    metrics: ChainMetricsCalculator
    agents: AgentFactorAnalyzer
    chain: ChainFactorAnalyzer
    technical: TechnicalFactorAnalyzer
    scorer: PredictionScorer
    strikes: StrikeSelector
    levels: PremiumLevelPlanner
    vix: Optional[VixFactorAnalyzer] = None
    breadth: Optional[BreadthFactorAnalyzer] = None
    mtf: Optional[MTFFactorAnalyzer] = None
    time_context: TimeContextAnalyzer
    clusters: FactorClusterSummarizer
    contributions: FactorContributionAnnotator
    regime: RawRegimeClassifier
    shadow: ChainShadowCalculator
    chart_shadow: ChartStructureShadowCalculator
    market_gate: PredictionMarketGate
    wait_gate: PredictionWaitGate
    adx_multiplier: AdxRegimeMultiplier
