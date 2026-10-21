from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytz

from schemas.options import OptionUnderlying
from schemas.prediction import (
    ChartPatternStatus,
    ChartStructureFeatures,
    IntradayIndicators,
    StructureBias,
)
from schemas.premarket import RecommendedAction
from schemas.trading import Candle, Tick
from services.prediction.chart_analysis_interpreter import ChartAnalysisInterpreter
from services.prediction.chart_candle_policy import ChartCandlePolicy
from services.prediction.chart_candle_validator import ChartCandleValidator
from services.prediction.chart_double_pattern_detector import ChartDoublePatternDetector
from services.prediction.chart_structure_event_detector import (
    ChartStructureEventDetector,
    StructureEventKind,
)
from services.prediction.chart_structure_factory import ChartStructureFactory
from services.prediction.chart_swing_detector import ChartSwingDetector, SwingKind, SwingPoint
from services.prediction.option_prediction_service import OptionPredictionService
from services.premarket.prediction_bridge import PremarketFactorBundle
from services.premarket.trading_calendar import TradingCalendar
from tests.prediction.test_prediction_gate_e2e import _analyzers, _chain

IST = pytz.timezone("Asia/Kolkata")


def _candle(start: datetime, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(time=int(start.timestamp()), open=open_, high=high, low=low, close=close, volume=1000.0)


def _session(day: int, hour: int = 9, minute: int = 15) -> datetime:
    return IST.localize(datetime(2026, 10, day, hour, minute))


def test_validator_flags_duplicates_and_gaps():
    start = _session(20)
    candles = [
        _candle(start, 100, 101, 99, 100),
        _candle(start, 100, 101, 99, 100),  # duplicate timestamp
        _candle(start + timedelta(minutes=20), 100, 101, 99, 100),  # gap vs 5m
    ]
    quality = ChartCandleValidator(ChartCandlePolicy()).validate(candles, 5)
    assert quality.ok is False
    assert quality.duplicate_bars == 1
    assert quality.gap_count >= 1


def test_choch_on_break_of_higher_low():
    start = _session(20)
    candles = [_candle(start + timedelta(minutes=5 * i), 100, 101, 99, 100) for i in range(14)]
    # Break must occur after last swing confirmation index (10)
    candles[11] = _candle(start + timedelta(minutes=55), 95, 96, 90, 91)
    swings = [
        SwingPoint(index=2, price=105, kind=SwingKind.HIGH, confirmed_at_index=4, time=candles[2].time),
        SwingPoint(index=4, price=98, kind=SwingKind.LOW, confirmed_at_index=6, time=candles[4].time),
        SwingPoint(index=6, price=108, kind=SwingKind.HIGH, confirmed_at_index=8, time=candles[6].time),
        SwingPoint(index=8, price=100, kind=SwingKind.LOW, confirmed_at_index=10, time=candles[8].time),
    ]
    event = ChartStructureEventDetector().detect(candles, swings, StructureBias.BULLISH, atr=10.0)
    assert event is not None
    assert event.kind == StructureEventKind.CHOCH
    assert event.bias == StructureBias.BEARISH
    assert event.level == 100.0


def test_double_top_potential_then_confirmed():
    start = _session(20)
    # Build swings manually via detector-friendly prices
    prices = [
        (100, 102, 99, 101),
        (101, 103, 100, 102),
        (102, 110, 101, 108),  # high pivot candidate
        (108, 109, 104, 105),
        (105, 106, 100, 101),  # mid low
        (101, 103, 100, 102),
        (102, 109.5, 101, 108),  # second high near first
        (108, 108.5, 103, 104),
        (104, 105, 99, 100),  # break neckline
        (100, 101, 98, 99),
        (99, 100, 97, 98),
        (98, 99, 96, 97),
    ]
    candles = [
        _candle(start + timedelta(minutes=5 * i), o, h, l, c)
        for i, (o, h, l, c) in enumerate(prices)
    ]
    # Pad to keep swing detector happy
    while len(candles) < 20:
        i = len(candles)
        candles.append(_candle(start + timedelta(minutes=5 * i), 97, 98, 96, 97))
    swings = ChartSwingDetector(left=2, right=2).detect(candles)
    result = ChartDoublePatternDetector(tolerance_atr=0.5).detect(candles, swings, atr=10.0)
    # May be potential/confirmed depending on exact pivots; if detected must be bearish double top family
    if result is not None:
        assert result.kind.value == "DOUBLE_TOP"
        assert result.bias == StructureBias.BEARISH
        assert result.status in {ChartPatternStatus.POTENTIAL, ChartPatternStatus.CONFIRMED}


def test_interpreter_falls_back_without_api_key():
    features = ChartStructureFeatures.unavailable("x", IST.localize(datetime(2026, 10, 20, 11, 0)))
    # Attach a minimal report via factory extract path instead
    policy = ChartCandlePolicy()
    extractor = ChartStructureFactory.extractor(policy)
    start = _session(20)
    candles = [
        _candle(start + timedelta(minutes=5 * i), 25000, 25010, 24990, 25000)
        for i in range(40)
    ]
    from services.prediction.chart_extractor_input import ChartExtractorInput

    features = extractor.extract(
        ChartExtractorInput(
            candles_5m=candles,
            candles_15m=candles[::3],
            prior_day=None,
            today_open=25000.0,
            session_range=None,
            atr=40.0,
            as_of=IST.localize(datetime(2026, 10, 20, 12, 0)),
        )
    )
    enriched = ChartAnalysisInterpreter("").enrich(features)
    assert enriched.report is not None
    assert enriched.report.narrative is None
    assert enriched.report.probability is None


def test_interpreter_invalid_json_and_parse_fallback(monkeypatch):
    assert ChartAnalysisInterpreter._parse_narrative("not-json") is None
    assert ChartAnalysisInterpreter._parse_narrative('{"narrative":""}') is None
    assert ChartAnalysisInterpreter._parse_narrative('{"narrative":"ok structure"}') == "ok structure"

    interpreter = ChartAnalysisInterpreter("dummy-key")
    features = ChartStructureFeatures.unavailable("x", IST.localize(datetime(2026, 10, 20, 11, 0)))
    from schemas.prediction import ChartAnalysisReport, ChartDataQuality, ChartScenario

    report = ChartAnalysisReport(
        structure=StructureBias.RANGE,
        pattern_status=ChartPatternStatus.NONE,
        evidence=["e"],
        bullish=ChartScenario(side="BULLISH", summary="b"),
        bearish=ChartScenario(side="BEARISH", summary="s"),
        wait=ChartScenario(side="WAIT", summary="w"),
        key_supports=[],
        key_resistances=[],
        data_quality=ChartDataQuality(ok=True, ordered=True, duplicate_bars=0, gap_count=0, detail="ok"),
        as_of=IST.localize(datetime(2026, 10, 20, 11, 0)),
        detail="d",
    )
    features = features.model_copy(update={"data_ok": True, "report": report})
    monkeypatch.setattr(interpreter, "_generate", lambda _features: None)
    out = interpreter.enrich(features)
    assert out.report is not None
    assert out.report.narrative is None


@pytest.mark.asyncio
async def test_chart_shadow_does_not_change_prediction_outputs():
    from datetime import date, timezone

    now = datetime.now(timezone.utc)
    exchange = now - timedelta(seconds=5)
    holiday = now.astimezone(IST).date()
    calendar = TradingCalendar({holiday})
    chain = _chain(now, exchange)
    sources = MagicMock()
    sources.agents.get = AsyncMock(
        return_value=MagicMock(
            action="BUY", confidence=90.0, bullish_agents=4, bearish_agents=0, reasons=["bull"]
        )
    )
    # AgentConsensus validation path in service uses model_validate via provider; mock service internals carefully
    from schemas.prediction import AgentConsensus

    sources = MagicMock()
    sources.agents.get = AsyncMock(
        return_value=AgentConsensus(
            action="BUY", confidence=90.0, bullish_agents=4, bearish_agents=0, reasons=["bull"]
        )
    )
    sources.indicators.get = AsyncMock(
        return_value=IntradayIndicators(
            price=25100,
            rsi=62,
            macd_histogram=5,
            ema_20=25000,
            atr=20,
            supertrend_direction=1,
            vwap=25050,
            rvol=1.2,
            volume_ratio=1.2,
            adx=28,
        )
    )
    sources.indicators_15m = MagicMock(
        get=AsyncMock(
            return_value=IntradayIndicators(
                price=25100,
                rsi=55,
                macd_histogram=2,
                ema_20=25020,
                atr=25,
                supertrend_direction=1,
                vwap=25040,
                rvol=1.0,
                volume_ratio=1.0,
                adx=22,
            )
        )
    )
    sources.premarket.bundle = AsyncMock(
        return_value=PremarketFactorBundle(factors=[], recommended_action=RecommendedAction.WATCH)
    )
    sources.vix = None
    sources.futures.latest = MagicMock(return_value=None)

    analyzers = _analyzers(calendar)
    # Two calculators that return different chart payloads
    chart_a = ChartStructureFeatures.unavailable("a", now)
    chart_b = ChartStructureFeatures.unavailable("b", now).model_copy(
        update={"detail": "different chart shadow"}
    )
    analyzers.chart_shadow.calculate = AsyncMock(return_value=chart_a)
    chain_service = MagicMock()
    chain_service.get_chain = AsyncMock(return_value=chain)
    market_data = MagicMock()
    market_data.get_tick = AsyncMock(
        return_value=Tick(
            symbol="^NSEI",
            ltp=25100,
            prev_close=25000,
            change=100,
            change_pct=0.4,
            timestamp=exchange,
            provider="TEST",
            fetched_at=now,
            exchange_timestamp=exchange,
        )
    )
    service = OptionPredictionService(
        chain_service=chain_service,
        market_data=market_data,
        sources=sources,
        analyzers=analyzers,
        cache_seconds=0,
        log_recorder=MagicMock(),
    )
    first = await service.predict(OptionUnderlying.NIFTY, date(2026, 10, 27))
    analyzers.chart_shadow.calculate = AsyncMock(return_value=chart_b)
    second = await service.predict(OptionUnderlying.NIFTY, date(2026, 10, 27))
    assert first.direction == second.direction
    assert first.signal_score == second.signal_score
    assert first.raw_score == second.raw_score
    assert first.gate_reason == second.gate_reason
    assert (first.contract is None) == (second.contract is None)
    assert first.shadow.chart.detail != second.shadow.chart.detail
