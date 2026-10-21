"""
End-to-end gate tests: a prediction that would otherwise select a contract must
return contract=null when market-closed, stale/unknown freshness, or WAIT fires.
"""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytz

from schemas.options import OptionChain, OptionChainRow, OptionQuote, OptionType, OptionUnderlying
from schemas.prediction import (
    AgentConsensus,
    ChartStructureFeatures,
    DataFreshness,
    GateReason,
    IntradayIndicators,
    PredictionDirection,
)
from schemas.premarket import MarketSentiment, RecommendedAction
from schemas.trading import Tick
from services.prediction.adx_regime_multiplier import AdxRegimeMultiplier
from services.prediction.agent_factor_analyzer import AgentFactorAnalyzer
from services.prediction.chain_factor_analyzer import ChainFactorAnalyzer
from services.prediction.chain_metrics_calculator import ChainMetricsCalculator
from services.prediction.chain_shadow_calculator import ChainShadowCalculator
from services.prediction.chart_structure_factory import ChartStructureFactory
from services.prediction.chart_structure_shadow_calculator import ChartStructureShadowCalculator
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.factor_cluster_summarizer import FactorClusterSummarizer
from services.prediction.factor_contribution_annotator import FactorContributionAnnotator
from services.prediction.option_prediction_service import OptionPredictionService
from services.prediction.prediction_dependencies import PredictionAnalyzers, PredictionSources
from services.prediction.prediction_market_gate import PredictionMarketGate
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.prediction_wait_gate import PredictionWaitGate
from services.prediction.prediction_weight_budget import PredictionWeightBudget
from services.prediction.premium_level_planner import PremiumLevelPlanner
from services.prediction.raw_regime_classifier import RawRegimeClassifier
from services.prediction.strike_selector import StrikeSelector
from services.prediction.strike_window_policy import StrikeWindowPolicy
from services.prediction.technical_factor_analyzer import TechnicalFactorAnalyzer
from services.prediction.time_context_analyzer import TimeContextAnalyzer
from services.premarket.prediction_bridge import PremarketFactorBundle
from services.premarket.trading_calendar import TradingCalendar

IST = pytz.timezone("Asia/Kolkata")
EXPIRY = date(2026, 10, 27)


def _quote(symbol: str, exchange_ts: Optional[datetime], fetched: datetime) -> OptionQuote:
    return OptionQuote(
        symbol=symbol,
        display_name=symbol,
        ltp=120.0,
        change=1.0,
        change_pct=1.0,
        open_interest=5000.0,
        volume=2000.0,
        bid=119.0,
        ask=121.0,
        fetched_at=fetched,
        exchange_timestamp=exchange_ts,
    )


def _chain(now: datetime, option_exchange_ts: Optional[datetime]) -> OptionChain:
    call = _quote("NIFTY27OCT2625000CE", option_exchange_ts, now)
    put = _quote("NIFTY27OCT2625000PE", option_exchange_ts, now)
    return OptionChain(
        underlying=OptionUnderlying.NIFTY,
        expiry=EXPIRY,
        spot=25000.0,
        atm_strike=25000.0,
        lot_size=65,
        rows=[
            OptionChainRow(strike=24900.0, call=_quote("C24900", option_exchange_ts, now), put=put),
            OptionChainRow(strike=25000.0, call=call, put=put),
            OptionChainRow(strike=25100.0, call=_quote("C25100", option_exchange_ts, now), put=put),
        ],
    )


def _indicators(price: float = 25100.0) -> IntradayIndicators:
    return IntradayIndicators(
        price=price,
        rsi=62.0,
        macd_histogram=5.0,
        ema_20=25000.0,
        atr=20.0,
        supertrend_direction=1,
        vwap=25050.0,
        rvol=1.2,
        volume_ratio=1.2,
        adx=28.0,
    )


def _chart_shadow() -> ChartStructureShadowCalculator:
    calculator = ChartStructureFactory.shadow_calculator(MagicMock(), "")
    calculator.calculate = AsyncMock(
        return_value=ChartStructureFeatures.unavailable("test shadow", datetime.now(timezone.utc))
    )
    return calculator


def _analyzers(calendar: TradingCalendar) -> PredictionAnalyzers:
    builder = PredictionFactorBuilder()
    windows = StrikeWindowPolicy({OptionUnderlying.NIFTY: 500.0, OptionUnderlying.BANKNIFTY: 1500.0})
    return PredictionAnalyzers(
        metrics=ChainMetricsCalculator(windows),
        agents=AgentFactorAnalyzer(builder, 0.12),
        chain=ChainFactorAnalyzer(builder, 500.0, 3),
        technical=TechnicalFactorAnalyzer(builder, "5m"),
        scorer=PredictionScorer(),
        strikes=StrikeSelector(),
        levels=PremiumLevelPlanner(),
        vix=None,
        breadth=None,
        mtf=None,
        time_context=TimeContextAnalyzer(),
        clusters=FactorClusterSummarizer(),
        contributions=FactorContributionAnnotator(),
        regime=RawRegimeClassifier(25.0, 20.0, 18.0),
        shadow=ChainShadowCalculator(windows),
        chart_shadow=_chart_shadow(),
        market_gate=PredictionMarketGate(calendar, 30.0),
        wait_gate=PredictionWaitGate(0.01, PredictionWeightBudget(0.12), 0.15, 50.0),
        adx_multiplier=AdxRegimeMultiplier(25.0, 20.0, 0.7, 1.0),
    )


def _service(
    calendar: TradingCalendar,
    chain: OptionChain,
    spot_tick: Tick,
    premarket_action: RecommendedAction = RecommendedAction.WATCH,
    indicators_15m: Optional[IntradayIndicators] = None,
) -> OptionPredictionService:
    sources = PredictionSources.model_construct(
        agents=MagicMock(get=AsyncMock(return_value=AgentConsensus(
            action="BUY", confidence=90.0, bullish_agents=4, bearish_agents=0, reasons=["bull"]
        ))),
        indicators=MagicMock(get=AsyncMock(return_value=_indicators())),
        indicators_15m=MagicMock(get=AsyncMock(return_value=indicators_15m or _indicators())),
        premarket=MagicMock(bundle=AsyncMock(return_value=PremarketFactorBundle(
            factors=[],
            recommended_action=premarket_action,
        ))),
        vix=None,
        futures=MagicMock(latest=MagicMock(return_value=None)),
    )
    chain_service = MagicMock()
    chain_service.get_chain = AsyncMock(return_value=chain)
    market_data = MagicMock()
    market_data.get_tick = AsyncMock(return_value=spot_tick)
    recorder = MagicMock()
    return OptionPredictionService(
        chain_service=chain_service,
        market_data=market_data,
        sources=sources,
        analyzers=_analyzers(calendar),
        cache_seconds=0,
        log_recorder=recorder,
    )


@pytest.mark.asyncio
async def test_would_select_contract_when_verified_fresh_and_open():
    now = IST.localize(datetime(2026, 10, 21, 10, 30)).astimezone(timezone.utc)
    exchange = now - timedelta(seconds=5)
    service = _service(
        TradingCalendar(set()),
        _chain(now, exchange),
        Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=exchange, provider="ANGEL", fetched_at=now, exchange_timestamp=exchange,
        ),
    )
    # Force "now" inside build by patching datetime in gate path via fresh exchange times near wall clock —
    # service uses datetime.now; align exchange to real now for this open-path smoke test.
    real_now = datetime.now(timezone.utc)
    if TradingCalendar(set()).session_phase(real_now) != "REGULAR":
        pytest.skip("open-path smoke requires REGULAR session in wall-clock IST")
    exchange = real_now - timedelta(seconds=5)
    service = _service(
        TradingCalendar(set()),
        _chain(real_now, exchange),
        Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=exchange, provider="ANGEL", fetched_at=real_now, exchange_timestamp=exchange,
        ),
    )
    prediction = await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    assert prediction.direction == PredictionDirection.CALL
    assert prediction.contract is not None
    assert prediction.gate_reason == GateReason.NONE
    assert prediction.data_freshness == DataFreshness.FRESH
    assert all(q.verified for q in prediction.quote_timestamps)


@pytest.mark.asyncio
async def test_market_closed_suppresses_contract():
    now = datetime.now(timezone.utc)
    exchange = now - timedelta(seconds=5)
    # Holiday forces MARKET_CLOSED regardless of wall clock
    holiday = now.astimezone(IST).date()
    service = _service(
        TradingCalendar({holiday}),
        _chain(now, exchange),
        Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=exchange, provider="ANGEL", fetched_at=now, exchange_timestamp=exchange,
        ),
    )
    prediction = await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    assert prediction.direction == PredictionDirection.MARKET_CLOSED
    assert prediction.contract is None
    assert prediction.gate_reason == GateReason.MARKET_CLOSED


@pytest.mark.asyncio
async def test_force_bypasses_prediction_cache():
    now = datetime.now(timezone.utc)
    exchange = now - timedelta(seconds=5)
    service = _service(
        TradingCalendar(set()),
        _chain(now, exchange),
        Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=exchange, provider="ANGEL", fetched_at=now, exchange_timestamp=exchange,
        ),
    )
    service._cache_seconds = 60.0
    builds = {"n": 0}
    original = service._build

    async def counted(underlying, expiry):
        builds["n"] += 1
        return await original(underlying, expiry)

    service._build = counted  # type: ignore[method-assign]
    await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    await service.predict(OptionUnderlying.NIFTY, EXPIRY, force=True)
    assert builds["n"] == 2


@pytest.mark.asyncio
async def test_unknown_freshness_suppresses_contract_that_would_otherwise_exist():
    now = datetime.now(timezone.utc)
    holiday = now.astimezone(IST).date()
    # Use a trading day calendar; if currently closed, still UNKNOWN after open check fails first —
    # inject REGULAR by using empty holiday set and only UNKNOWN freshness.
    calendar = TradingCalendar(set())
    service = _service(
        calendar,
        _chain(now, None),  # option has no exchange timestamp
        Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=now, provider="YAHOO", fetched_at=now, exchange_timestamp=None,
        ),
    )
    prediction = await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    if calendar.session_phase(now) != "REGULAR":
        assert prediction.direction == PredictionDirection.MARKET_CLOSED
        assert prediction.contract is None
    else:
        assert prediction.direction == PredictionDirection.UNKNOWN_FRESHNESS
        assert prediction.contract is None
        assert prediction.gate_reason == GateReason.UNKNOWN_FRESHNESS


@pytest.mark.asyncio
async def test_stale_exchange_timestamp_suppresses_contract():
    now = datetime.now(timezone.utc)
    calendar = TradingCalendar(set())
    stale = now - timedelta(seconds=120)
    service = _service(
        calendar,
        _chain(now, stale),
        Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=stale, provider="ANGEL", fetched_at=now, exchange_timestamp=stale,
        ),
    )
    prediction = await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    if calendar.session_phase(now) != "REGULAR":
        assert prediction.contract is None
        assert prediction.direction == PredictionDirection.MARKET_CLOSED
    else:
        assert prediction.direction == PredictionDirection.STALE_DATA
        assert prediction.contract is None
        assert prediction.gate_reason == GateReason.STALE_DATA


@pytest.mark.asyncio
async def test_wait_premarket_suppresses_contract_on_open_verified_path():
    now = datetime.now(timezone.utc)
    calendar = TradingCalendar(set())
    if calendar.session_phase(now) != "REGULAR":
        pytest.skip("WAIT e2e requires REGULAR session")
    exchange = now - timedelta(seconds=5)
    service = _service(
        calendar,
        _chain(now, exchange),
        Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=exchange, provider="ANGEL", fetched_at=now, exchange_timestamp=exchange,
        ),
        premarket_action=RecommendedAction.WAIT,
    )
    prediction = await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    assert prediction.direction == PredictionDirection.WAIT
    assert prediction.contract is None
    assert prediction.gate_reason == GateReason.PREMARKET_WAIT


@pytest.mark.asyncio
async def test_mtf_conflict_wait_suppresses_contract():
    now = datetime.now(timezone.utc)
    calendar = TradingCalendar(set())
    if calendar.session_phase(now) != "REGULAR":
        pytest.skip("MTF WAIT e2e requires REGULAR session")
    exchange = now - timedelta(seconds=5)
    builders = _analyzers(calendar)
    # Enable MTF on analyzers
    from services.prediction.mtf_factor_analyzer import MTFFactorAnalyzer
    analyzers = builders.model_copy(update={
        "mtf": MTFFactorAnalyzer(PredictionFactorBuilder()),
    })
    sources = PredictionSources.model_construct(
        agents=MagicMock(get=AsyncMock(return_value=AgentConsensus(
            action="BUY", confidence=90.0, bullish_agents=4, bearish_agents=0, reasons=["bull"]
        ))),
        indicators=MagicMock(get=AsyncMock(return_value=_indicators(25100))),
        indicators_15m=MagicMock(get=AsyncMock(return_value=_indicators(24900))),  # conflict vs ema 25000
        premarket=MagicMock(bundle=AsyncMock(return_value=PremarketFactorBundle(
            factors=[], recommended_action=RecommendedAction.WATCH,
        ))),
        vix=None,
        futures=MagicMock(latest=MagicMock(return_value=None)),
    )
    service = OptionPredictionService(
        chain_service=MagicMock(get_chain=AsyncMock(return_value=_chain(now, exchange))),
        market_data=MagicMock(get_tick=AsyncMock(return_value=Tick(
            symbol="^NSEI", ltp=25100, prev_close=25000, change=100, change_pct=0.4,
            timestamp=exchange, provider="ANGEL", fetched_at=now, exchange_timestamp=exchange,
        ))),
        sources=sources,
        analyzers=analyzers,
        cache_seconds=0,
        log_recorder=MagicMock(),
    )
    prediction = await service.predict(OptionUnderlying.NIFTY, EXPIRY)
    assert prediction.direction == PredictionDirection.WAIT
    assert prediction.contract is None
    assert prediction.gate_reason == GateReason.MTF_CONFLICT
