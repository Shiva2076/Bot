from datetime import datetime, timedelta
from typing import List

import pytz

from schemas.prediction import SessionRange, SessionRangeKind, StructureBias
from schemas.trading import Candle
from services.prediction.chart_breakout_detector import BreakoutKind, ChartBreakoutDetector
from services.prediction.chart_candle_policy import ChartCandlePolicy
from services.prediction.chart_extractor_input import ChartExtractorInput
from services.prediction.chart_fvg_detector import ChartFvgDetector, FvgSide
from services.prediction.chart_liquidity_sweep_detector import ChartLiquiditySweepDetector, SweepSide
from services.prediction.chart_prior_day_levels import ChartPriorDayLevelBuilder
from services.prediction.chart_structure_factory import ChartStructureFactory
from services.prediction.chart_structure_mapper import ChartStructureMapper
from services.prediction.chart_structure_shadow_calculator import ChartStructureShadowCalculator
from services.prediction.chart_swing_detector import ChartSwingDetector, SwingKind

IST = pytz.timezone("Asia/Kolkata")


def _candle(start: datetime, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        time=int(start.timestamp()),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
    )


def _session_start(day: int, hour: int = 9, minute: int = 15) -> datetime:
    return IST.localize(datetime(2026, 10, day, hour, minute))


def _flat_series(day: int, count: int, base: float = 25000.0) -> List[Candle]:
    start = _session_start(day)
    return [
        _candle(start + timedelta(minutes=5 * i), base, base + 5, base - 5, base + 1)
        for i in range(count)
    ]


def test_swing_requires_right_bars_before_confirmation():
    start = _session_start(20)
    # Pivot high at index 2; needs indexes 3 and 4 before confirmation (right=2)
    candles = [
        _candle(start + timedelta(minutes=5 * i), 100, h, l, 100)
        for i, (h, l) in enumerate(
            [(101, 99), (102, 98), (110, 100), (103, 99), (102, 98), (101, 97)]
        )
    ]
    detector = ChartSwingDetector(left=2, right=2)
    before_confirm = detector.detect(candles[:5])  # only through index 4 = confirmed_at for pivot 2
    assert any(p.index == 2 and p.kind == SwingKind.HIGH for p in before_confirm)

    too_early = detector.detect(candles[:4])  # missing right bar at index 4
    assert not any(p.index == 2 for p in too_early)


def test_swing_no_lookahead_on_last_unconfirmed_bar():
    start = _session_start(20)
    candles = [
        _candle(start + timedelta(minutes=5 * i), 100, 100 + i, 99, 100)
        for i in range(6)
    ]
    # Make index 4 a local high but without two right bars in a 6-bar series (indexes 0..5)
    candles[4] = _candle(start + timedelta(minutes=20), 100, 120, 99, 100)
    points = ChartSwingDetector(left=2, right=2).detect(candles)
    assert not any(p.index == 4 for p in points)


def test_break_and_retest_support():
    start = _session_start(20)
    support = 25000.0
    candles = [
        _candle(start, 25010, 25020, 25005, 25012),
        _candle(start + timedelta(minutes=5), 25012, 25015, 24980, 24985),  # break down
        _candle(start + timedelta(minutes=10), 24985, 25002, 24970, 24990),  # retest reject
        _candle(start + timedelta(minutes=15), 24990, 24995, 24960, 24970),
    ]
    result = ChartBreakoutDetector(epsilon_atr_fraction=0.01, retest_tolerance_atr=0.2, retest_bars=4).detect(
        candles, resistance=25100.0, support=support, atr=50.0, resistance_label="R", support_label="S"
    )
    assert result.kind == BreakoutKind.BREAK_DOWN_RETEST


def test_liquidity_sweep_noise_floor_rejects_tiny_wick():
    start = _session_start(20)
    level = 25000.0
    # Tiny wick above level — body small but wick only 2 pts < max(0.25*ATR=12.5, 8)
    candles = [_candle(start, 24990, 25002, 24985, 24988)]
    result = ChartLiquiditySweepDetector().detect(
        candles, resistance=level, support=24900.0, atr=50.0, resistance_label="PDH", support_label="PDL"
    )
    assert result.side == SweepSide.NONE


def test_liquidity_sweep_detects_valid_bearish_rejection():
    start = _session_start(20)
    level = 25000.0
    candles = [_candle(start, 24990, 25030, 24980, 24985)]  # upper wick 40, body 5
    result = ChartLiquiditySweepDetector().detect(
        candles, resistance=level, support=24900.0, atr=50.0, resistance_label="PDH", support_label="PDL"
    )
    assert result.side == SweepSide.BEARISH
    assert result.level == level


def test_fvg_skips_overnight_session_boundary():
    policy = ChartCandlePolicy()
    # 15:25 previous day, then 09:15/09:20 next day — must not form overnight FVG
    left = _candle(_session_start(19, 15, 25), 25000, 25010, 24990, 25005)
    mid = _candle(_session_start(20, 9, 15), 25100, 25150, 25090, 25140)
    right = _candle(_session_start(20, 9, 20), 25140, 25160, 25130, 25150)
    # Bullish geometric FVG would exist if session ignored (right.low 25130 > left.high 25010)
    gaps = ChartFvgDetector(policy).detect([left, mid, right])
    assert gaps == []


def test_fvg_forms_within_same_session():
    policy = ChartCandlePolicy()
    start = _session_start(20)
    left = _candle(start, 25000, 25010, 24990, 25005)
    mid = _candle(start + timedelta(minutes=5), 25005, 25080, 25000, 25070)
    right = _candle(start + timedelta(minutes=10), 25070, 25090, 25040, 25060)  # low 25040 > left high 25010
    gaps = ChartFvgDetector(policy).detect([left, mid, right])
    assert len(gaps) == 1
    assert gaps[0].side == FvgSide.BULLISH
    assert gaps[0].bottom == 25010.0
    assert gaps[0].top == 25040.0


def test_candle_policy_drops_forming_bar():
    policy = ChartCandlePolicy()
    start = _session_start(20, 10, 0)
    candles = [
        _candle(start, 100, 101, 99, 100),
        _candle(start + timedelta(minutes=5), 100, 102, 99, 101),  # forming if as_of < 10:10
    ]
    as_of = start + timedelta(minutes=7)  # 10:07 — second 5m bar still open
    completed = policy.completed(candles, 5, as_of)
    assert len(completed) == 1
    assert completed[0].time == candles[0].time


def test_prior_day_levels_from_daily_candles():
    policy = ChartCandlePolicy()
    builder = ChartPriorDayLevelBuilder(policy)
    prior = _candle(IST.localize(datetime(2026, 10, 19, 0, 0)), 24900, 25100, 24800, 25050)
    today = _candle(IST.localize(datetime(2026, 10, 20, 0, 0)), 25060, 25200, 25000, 25100)
    as_of = IST.localize(datetime(2026, 10, 20, 11, 0))
    levels = builder.build([prior, today], as_of)
    assert levels is not None
    assert levels.pdh == 25100.0
    assert levels.pdl == 24800.0
    assert levels.pdc == 25050.0


def test_extractor_unavailable_on_missing_bars():
    extractor = ChartStructureFactory.extractor(ChartCandlePolicy())
    result = extractor.extract(
        ChartExtractorInput(
            candles_5m=_flat_series(20, 5),
            candles_15m=[],
            prior_day=None,
            today_open=None,
            session_range=None,
            atr=50.0,
            as_of=IST.localize(datetime(2026, 10, 20, 11, 0)),
        )
    )
    assert result.data_ok is False
    assert result.probability is None
    assert result.action_hint == "WAIT"


def test_shadow_calculator_fail_safe_on_invalid_atr():
    policy = ChartCandlePolicy()
    calc = ChartStructureShadowCalculator(
        market_data=object(),
        mapper=ChartStructureMapper(policy, ChartPriorDayLevelBuilder(policy)),
        extractor=ChartStructureFactory.extractor(policy),
    )
    as_of = IST.localize(datetime(2026, 10, 20, 11, 0))
    result = calc.calculate_from_candles(
        candles_5m=_flat_series(20, 40),
        candles_15m=_flat_series(20, 20),
        daily_candles=[_candle(IST.localize(datetime(2026, 10, 19, 0, 0)), 1, 2, 0.5, 1.5)],
        session_range=SessionRange(kind=SessionRangeKind.OPENING_RANGE, minutes=15, high=25020, low=24980),
        atr=0.0,
        as_of=as_of,
    )
    assert result.data_ok is False
    assert result.probability is None


def test_extractor_includes_opening_gap_and_keeps_probability_null():
    policy = ChartCandlePolicy()
    extractor = ChartStructureFactory.extractor(policy)
    as_of = IST.localize(datetime(2026, 10, 20, 11, 0))
    prior = ChartPriorDayLevelBuilder(policy).build(
        [_candle(IST.localize(datetime(2026, 10, 19, 0, 0)), 24900, 25100, 24800, 25000)],
        as_of,
    )
    result = extractor.extract(
        ChartExtractorInput(
            candles_5m=_flat_series(20, 40, base=25010.0),
            candles_15m=_flat_series(20, 20, base=25010.0),
            prior_day=prior,
            today_open=25040.0,
            session_range=SessionRange(kind=SessionRangeKind.INITIAL_BALANCE, minutes=60, high=25050, low=24970),
            atr=40.0,
            as_of=as_of,
        )
    )
    assert result.data_ok is True
    assert result.probability is None
    assert result.opening_gap_points == 40.0
    assert result.report is not None
    assert result.report.probability is None
    assert result.annotations
    assert result.structure_5m in {StructureBias.BULLISH, StructureBias.BEARISH, StructureBias.RANGE}
