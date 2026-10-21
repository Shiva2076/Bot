import httpx

from config import settings
from schemas.angel import AngelCredentials
from schemas.options import OptionUnderlying
from schemas.trading import CandleInterval
from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.brokers.angel.provider import AngelProvider
from services.brokers.angel.rate_limiter import SlidingWindowRateLimiter
from services.brokers.angel.quote_mapper import AngelQuoteMapper
from services.brokers.angel.session import AngelSession
from services.market_data import market_data_service
from services.options.black_scholes_model import BlackScholesModel
from services.options.expiry_settlement_policy import ExpirySettlementPolicy
from services.options.option_chain_service import OptionChainService
from services.options.option_greeks_enricher import OptionGreeksEnricher
from services.options.option_symbol_parser import OptionSymbolParser
from schemas.costs import CostConfig
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.premarket.breadth_collector import BreadthCollector
from services.risk.daily_risk_state import DailyRiskState
from services.risk.pre_trade_risk_gate import PreTradeRiskGate
from services.risk.position_sizer import PositionSizer
from services.premarket.gift_nifty_provider import GiftNiftyProvider
from services.premarket.global_markets_collector import GlobalMarketsCollector
from services.premarket.india_vix_provider import IndiaVixProvider
from services.premarket.news_risk_collector import NewsRiskCollector
from services.premarket.nifty_context_collector import NiftyContextCollector
from services.premarket.prediction_bridge import PremarketPredictionBridge
from services.premarket.premarket_analyzer_service import PremarketAnalyzerService
from services.premarket.premarket_dependencies import PremarketCollectors, PremarketEngines
from services.premarket.premarket_factor_analyzer import PremarketFactorAnalyzer
from services.premarket.premarket_scorer import PremarketScorer
from services.premarket.scheduler import PremarketScheduler
from services.premarket.sector_collector import SectorCollector
from services.premarket.sentiment_classifier import SentimentClassifier
from services.premarket.trading_calendar import TradingCalendar
from services.prediction.agent_consensus_provider import AgentConsensusProvider
from services.prediction.agent_factor_analyzer import AgentFactorAnalyzer
from services.prediction.breadth_factor_analyzer import BreadthFactorAnalyzer
from services.prediction.chain_factor_analyzer import ChainFactorAnalyzer
from services.prediction.chain_metrics_calculator import ChainMetricsCalculator
from services.prediction.adx_regime_multiplier import AdxRegimeMultiplier
from services.prediction.chain_shadow_calculator import ChainShadowCalculator
from services.prediction.chart_structure_factory import ChartStructureFactory
from services.prediction.chart_structure_query_service import ChartStructureQueryService
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.factor_cluster_summarizer import FactorClusterSummarizer
from services.prediction.factor_contribution_annotator import FactorContributionAnnotator
from services.prediction.futures_flow_tracker import FuturesFlowTracker
from services.prediction.intraday_indicator_provider import IntradayIndicatorProvider
from services.prediction.mtf_factor_analyzer import MTFFactorAnalyzer
from services.prediction.option_prediction_service import OptionPredictionService
from services.prediction.prediction_dependencies import PredictionAnalyzers, PredictionSources
from services.prediction.prediction_log_mapper import PredictionLogMapper
from services.prediction.prediction_log_query_service import PredictionLogQueryService
from services.prediction.prediction_log_recorder import PredictionLogRecorder
from services.prediction.prediction_market_gate import PredictionMarketGate
from services.prediction.prediction_outcome_calculator import PredictionOutcomeCalculator
from services.prediction.prediction_outcome_monitor import PredictionOutcomeMonitor
from services.prediction.prediction_outcome_resolver import PredictionOutcomeResolver
from services.prediction.prediction_wait_gate import PredictionWaitGate
from services.prediction.prediction_weight_budget import PredictionWeightBudget
from services.prediction.premium_level_planner import PremiumLevelPlanner
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.raw_regime_classifier import RawRegimeClassifier
from services.prediction.session_range_calculator import SessionRangeCalculator
from services.prediction.strike_selector import StrikeSelector
from services.prediction.strike_window_policy import StrikeWindowPolicy
from services.prediction.technical_factor_analyzer import TechnicalFactorAnalyzer
from services.prediction.time_context_analyzer import TimeContextAnalyzer
from services.prediction.vix_factor_analyzer import VixFactorAnalyzer
from services.snapshots.market_snapshot_mapper import MarketSnapshotMapper
from services.snapshots.market_snapshot_monitor import MarketSnapshotMonitor
from services.snapshots.market_snapshot_recorder import MarketSnapshotDependencies, MarketSnapshotRecorder
from services.trading.failover_market_data import FailoverMarketData
from services.trading.instrument_catalog import InstrumentCatalog
from services.trading.instrument_resolver import InstrumentResolver
from services.trading.risk_monitor import RiskMonitor
from services.trading.stop_target_evaluator import StopTargetEvaluator
from services.trading.yahoo_provider import YahooProvider

PREDICTION_INTERVAL = CandleInterval.FIVE_MINUTES
PREDICTION_INTERVAL_15M = CandleInterval.FIFTEEN_MINUTES

http_client = httpx.AsyncClient(timeout=15)
option_symbol_parser = OptionSymbolParser()
angel_quote_mapper = AngelQuoteMapper()
angel_master = AngelInstrumentMaster(http_client, option_symbol_parser)
angel_provider = AngelProvider(
    session=AngelSession(
        AngelCredentials(
            api_key=settings.angel_api_key,
            client_code=settings.angel_client_code,
            pin=settings.angel_pin,
            totp_secret=settings.angel_totp_secret,
        ),
        http_client,
        SlidingWindowRateLimiter(
            max_requests=settings.angel_requests_per_second,
            window_seconds=1.0,
        ),
        max_concurrent_requests=settings.angel_max_concurrent_requests,
    ),
    master=angel_master,
    mapper=angel_quote_mapper,
    quote_cache_seconds=settings.angel_quote_cache_seconds,
)

market_data = FailoverMarketData([angel_provider, YahooProvider(settings.tick_cache_seconds)])
instrument_catalog = InstrumentCatalog(settings)
instrument_resolver = InstrumentResolver(instrument_catalog, angel_master)
option_chain_service = OptionChainService(
    angel_master,
    angel_provider,
    market_data,
    angel_quote_mapper,
    OptionGreeksEnricher(
        BlackScholesModel(min_vol=0.01, max_vol=3.0, iterations=100, tolerance=1e-4),
        settings.options_risk_free_rate,
    ),
)
strike_window_policy = StrikeWindowPolicy({
    OptionUnderlying.NIFTY: settings.prediction_strike_window_nifty,
    OptionUnderlying.BANKNIFTY: settings.prediction_strike_window_banknifty,
})
chain_shadow_calculator = ChainShadowCalculator(strike_window_policy)
chart_structure_shadow_calculator = ChartStructureFactory.shadow_calculator(
    market_data, settings.gemini_api_key
)
futures_flow_tracker = FuturesFlowTracker(angel_master, angel_provider, angel_quote_mapper)
session_range_calculator = SessionRangeCalculator(
    initial_balance_minutes=settings.prediction_initial_balance_minutes,
    opening_range_minutes=settings.prediction_opening_range_minutes,
)
chart_structure_query_service = ChartStructureQueryService(
    market_data=market_data,
    calculator=chart_structure_shadow_calculator,
    session_ranges=session_range_calculator,
)

trading_calendar = TradingCalendar(TradingCalendar.parse_holidays(settings.premarket_nse_holidays))
sentiment_classifier = SentimentClassifier(
    settings.premarket_sentiment_bullish_pct,
    settings.premarket_sentiment_bearish_pct,
)
premarket_analyzer_service = PremarketAnalyzerService(
    collectors=PremarketCollectors(
        calendar=trading_calendar,
        global_markets=GlobalMarketsCollector(market_data, sentiment_classifier),
        gift=GiftNiftyProvider(),
        vix=IndiaVixProvider(market_data, settings.premarket_vix_low, settings.premarket_vix_high),
        breadth=BreadthCollector(market_data_service, trading_calendar),
        nifty=NiftyContextCollector(market_data, market_data_service, trading_calendar),
        sectors=SectorCollector(),
        news=NewsRiskCollector(),
    ),
    engines=PremarketEngines(
        factors=PremarketFactorAnalyzer(
            global_weight=settings.premarket_weight_global,
            gift_weight=settings.premarket_weight_gift,
            breadth_weight=settings.premarket_weight_breadth,
            nifty_weight=settings.premarket_weight_nifty,
            news_weight=settings.premarket_weight_news,
            sector_weight=settings.premarket_weight_sector,
            large_gap_pct=settings.premarket_large_gap_pct,
        ),
        scorer=PremarketScorer(
            bullish_threshold=settings.premarket_score_bullish,
            bearish_threshold=settings.premarket_score_bearish,
            min_included_factors=settings.premarket_min_factors,
            large_gap_pct=settings.premarket_large_gap_pct,
        ),
    ),
    cache_seconds=settings.premarket_cache_seconds,
)
prediction_factor_builder = PredictionFactorBuilder()
premarket_prediction_bridge = PremarketPredictionBridge(premarket_analyzer_service, prediction_factor_builder)
premarket_scheduler = PremarketScheduler(
    analyzer=premarket_analyzer_service,
    calendar=trading_calendar,
    run_hour=settings.premarket_scheduler_hour,
    run_minute=settings.premarket_scheduler_minute,
)
vix_provider_for_prediction = IndiaVixProvider(
    market_data, settings.premarket_vix_low, settings.premarket_vix_high
)
prediction_log_mapper = PredictionLogMapper(settings.prediction_scorer_version, settings.prediction_data_version)
prediction_log_recorder = PredictionLogRecorder(prediction_log_mapper)
prediction_log_query_service = PredictionLogQueryService(prediction_log_mapper)
option_prediction_service = OptionPredictionService(
    chain_service=option_chain_service,
    market_data=market_data,
    sources=PredictionSources(
        agents=AgentConsensusProvider(settings.agent_consensus_cache_seconds),
        indicators=IntradayIndicatorProvider(market_data, PREDICTION_INTERVAL, session_range_calculator),
        indicators_15m=IntradayIndicatorProvider(market_data, PREDICTION_INTERVAL_15M, session_range_calculator),
        premarket=premarket_prediction_bridge,
        vix=vix_provider_for_prediction,
        futures=futures_flow_tracker,
    ),
    analyzers=PredictionAnalyzers(
        metrics=ChainMetricsCalculator(strike_window_policy),
        agents=AgentFactorAnalyzer(prediction_factor_builder, settings.prediction_agent_weight),
        chain=ChainFactorAnalyzer(
            prediction_factor_builder,
            oi_wall_proximity_points=settings.prediction_oi_wall_proximity_points,
            max_pain_zero_dte=settings.prediction_max_pain_zero_dte,
        ),
        technical=TechnicalFactorAnalyzer(prediction_factor_builder, PREDICTION_INTERVAL.value),
        scorer=PredictionScorer(),
        strikes=StrikeSelector(),
        levels=PremiumLevelPlanner(),
        vix=VixFactorAnalyzer(prediction_factor_builder),
        breadth=BreadthFactorAnalyzer(prediction_factor_builder),
        mtf=MTFFactorAnalyzer(prediction_factor_builder),
        time_context=TimeContextAnalyzer(),
        clusters=FactorClusterSummarizer(),
        contributions=FactorContributionAnnotator(),
        regime=RawRegimeClassifier(
            trend_adx=settings.prediction_regime_trend_adx,
            range_adx=settings.prediction_regime_range_adx,
            volatile_vix=settings.premarket_vix_high,
        ),
        shadow=chain_shadow_calculator,
        chart_shadow=chart_structure_shadow_calculator,
        market_gate=PredictionMarketGate(
            trading_calendar, settings.prediction_max_quote_age_seconds
        ),
        wait_gate=PredictionWaitGate(
            min_coverage=settings.prediction_min_coverage,
            weight_budget=PredictionWeightBudget(settings.prediction_agent_weight),
            cluster_disagreement_epsilon=settings.prediction_cluster_disagreement_epsilon,
            min_signal_score=settings.prediction_min_signal_score,
        ),
        adx_multiplier=AdxRegimeMultiplier(
            trend_adx=settings.prediction_regime_trend_adx,
            range_adx=settings.prediction_regime_range_adx,
            range_multiplier=settings.prediction_adx_range_multiplier,
            trend_multiplier=settings.prediction_adx_trend_multiplier,
        ),
    ),
    cache_seconds=settings.prediction_cache_seconds,
    log_recorder=prediction_log_recorder,
)
market_snapshot_monitor = MarketSnapshotMonitor(
    recorder=MarketSnapshotRecorder(MarketSnapshotDependencies(
        chains=option_chain_service,
        shadow=chain_shadow_calculator,
        futures=futures_flow_tracker,
        mapper=MarketSnapshotMapper(settings.prediction_data_version),
    )),
    calendar=trading_calendar,
    underlyings=[OptionUnderlying(u.strip()) for u in settings.snapshot_underlyings.split(",") if u.strip()],
    interval_seconds=settings.snapshot_interval_seconds,
)
paper_cost_calculator = PaperCostCalculator(
    CostConfig(
        brokerage_pct=settings.cost_brokerage_pct,
        brokerage_flat=settings.cost_brokerage_flat,
        exchange_txn_pct=settings.cost_exchange_txn_pct,
        sebi_pct=settings.cost_sebi_pct,
        stamp_duty_buy_pct=settings.cost_stamp_duty_buy_pct,
        stt_sell_pct=settings.cost_stt_sell_pct,
        gst_pct=settings.cost_gst_pct,
        slippage_bps=settings.cost_slippage_bps,
    )
)
prediction_outcome_resolver = PredictionOutcomeResolver(
    market_data=market_data,
    calculator=PredictionOutcomeCalculator(settings.prediction_outcome_flat_band_pct, paper_cost_calculator),
)
prediction_outcome_monitor = PredictionOutcomeMonitor(
    resolver=prediction_outcome_resolver,
    interval_seconds=settings.prediction_outcome_monitor_seconds,
)
pre_trade_risk_gate = PreTradeRiskGate(
    max_data_age_seconds=settings.risk_max_data_age_seconds,
    max_risk_per_trade_pct=settings.risk_per_trade_pct,
    daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
    max_open_positions=settings.risk_max_open_positions,
    cost_calculator=paper_cost_calculator,
)
daily_risk_state = DailyRiskState()
position_sizer = PositionSizer(settings.risk_per_trade_pct)
risk_monitor = RiskMonitor(
    market_data=market_data,
    evaluator=StopTargetEvaluator(),
    parser=option_symbol_parser,
    expiry_policy=ExpirySettlementPolicy(),
    mapper=PersonalTradeMapper(PnlCalculator()),
    costs=paper_cost_calculator,
    interval_seconds=settings.risk_monitor_interval_seconds,
)
