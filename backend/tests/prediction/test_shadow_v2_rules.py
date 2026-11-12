"""Fixed-input tests for every Phase 2 (v2.0 shadow) rule, including boundaries."""
from datetime import date, datetime, timedelta

import pytest
import pytz

from schemas.prediction import (
    ChainShadowFeatures,
    FactorBias,
    FactorCluster,
    FactorStatus,
    IvRankGateStatus,
    OptionPrediction,
    PredictionDirection,
    RegimeLabel,
    RegimeSnapshot,
    ShadowFeatures,
)
from schemas.shadow_v2 import ChainSnapshotPoint, DailyAtmIv, ShadowV2Config, ShadowV2Inputs
from schemas.trading import Candle
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.v2.factory import build_shadow_scorer_v2
from services.prediction.v2.futures_volume_analyzer import (
    FUTURES_RVOL_NAME,
    FUTURES_VWAP_NAME,
    FuturesVolumeAnalyzer,
)
from services.prediction.v2.iv_rank_gate import IvRankGateEvaluator
from services.prediction.v2.oi_buildup_analyzer import OiBuildupAnalyzer, OiBuildupMode
from services.prediction.v2.pcr_change_analyzer import PcrChangeAnalyzer
from services.prediction.v2.premarket_half_life import PREMARKET_V2_NAME, PremarketHalfLifeAnalyzer
from services.prediction.v2.shadow_scorer_v2 import IV_RANK_GATE_REASON
from services.prediction.v2.snapshot_history import daily_atm_iv_series, snapshot_near

IST = pytz.timezone("Asia/Kolkata")
B = PredictionFactorBuilder()
NOW = IST.localize(datetime(2026, 11, 13, 11, 0))
EXPIRY = date(2026, 11, 17)


def point(minutes_ago: float, *, pcr=None, call=1000.0, put=1000.0, spot=25000.0, window=500.0,
          expiry=EXPIRY, iv=None, at=None) -> ChainSnapshotPoint:
    return ChainSnapshotPoint(
        captured_at=at or (NOW - timedelta(minutes=minutes_ago)), expiry=expiry, spot=spot,
        strike_window=window, near_call_oi=call, near_put_oi=put, near_spot_pcr=pcr, atm_iv=iv,
    )


# ── snapshot lookup ──────────────────────────────────────────────────────────

def test_snapshot_near_picks_closest_within_tolerance_and_window():
    history = [point(19, pcr=1.0), point(16, pcr=1.1), point(15, pcr=1.2, window=1500), point(13, pcr=1.3)]
    chosen = snapshot_near(history, NOW - timedelta(minutes=15), 4, strike_window=500)
    assert chosen.near_spot_pcr == 1.1          # 16m ago is 1m off; the 15m one has another window
    assert snapshot_near(history, NOW - timedelta(minutes=40), 4) is None


# ── PCR change ───────────────────────────────────────────────────────────────

def pcr_analyzer():
    return PcrChangeAnalyzer(B, weight=0.10, window_minutes=15, tolerance_minutes=4, full_scale=0.10)


def test_pcr_change_unavailable_without_current_or_history():
    assert pcr_analyzer().analyze(None, 500, NOW, [point(15, pcr=1.0)]).status == FactorStatus.UNAVAILABLE
    assert pcr_analyzer().analyze(1.0, 500, NOW, []).status == FactorStatus.UNAVAILABLE


def test_pcr_change_tolerance_boundary_is_inclusive():
    at_edge = pcr_analyzer().analyze(1.05, 500, NOW, [point(19, pcr=1.0)])     # exactly 4m off
    beyond = pcr_analyzer().analyze(1.05, 500, NOW, [point(19.1, pcr=1.0)])
    assert at_edge.status == FactorStatus.ACTIVE
    assert beyond.status == FactorStatus.UNAVAILABLE


def test_pcr_change_score_sign_scale_and_clamp():
    rising = pcr_analyzer().analyze(1.05, 500, NOW, [point(15, pcr=1.0)])
    falling = pcr_analyzer().analyze(0.95, 500, NOW, [point(15, pcr=1.0)])
    huge = pcr_analyzer().analyze(1.5, 500, NOW, [point(15, pcr=1.0)])
    assert rising.score == pytest.approx(0.5) and rising.bias == FactorBias.BULLISH
    assert falling.score == pytest.approx(-0.5) and falling.bias == FactorBias.BEARISH
    assert huge.score == 1.0
    assert rising.weight == 0.10 and rising.cluster == FactorCluster.OPTIONS


# ── ΔOI buildup ──────────────────────────────────────────────────────────────

def oi_analyzer():
    return OiBuildupAnalyzer(B, weight=0.07, window_minutes=15, tolerance_minutes=4,
                             min_oi_change_pct=1.0, min_price_change_pct=0.05, full_scale_pct=5.0)


@pytest.mark.parametrize("price, d_call, d_put, mode", [
    (0.04, -3.0, 3.0, OiBuildupMode.NONE),            # price below min move
    (0.05, 0.0, 1.0, OiBuildupMode.PUT_WRITING),      # boundaries inclusive
    (0.20, -1.0, 0.0, OiBuildupMode.CALL_UNWINDING),
    (0.20, 0.0, 0.99, OiBuildupMode.NONE),            # OI move below min
    (0.20, 2.0, 1.5, OiBuildupMode.NONE),             # price up but call OI grew faster: contradicts
    (-0.05, 1.0, 0.0, OiBuildupMode.CALL_WRITING),
    (-0.20, 0.0, -1.0, OiBuildupMode.PUT_UNWINDING),
    (-0.20, 0.5, 2.0, OiBuildupMode.NONE),            # price down but net writer flow bullish
])
def test_oi_buildup_modes(price, d_call, d_put, mode):
    assert oi_analyzer().classify(price, d_call, d_put) == mode


def test_oi_buildup_factor_active_neutral_unavailable():
    past = point(15, call=1000, put=1000, spot=25000)            # near OI base 2000
    bullish = oi_analyzer().analyze(25050, 1000, 1100, 500, NOW, [past])   # +0.2%, put +5% → net +5%
    assert bullish.status == FactorStatus.ACTIVE and bullish.score == 1.0 and bullish.weight == 0.07
    assert "PUT_WRITING" in bullish.detail
    bearish = oi_analyzer().analyze(24950, 1040, 1000, 500, NOW, [past])   # call +2% → net -2%
    assert bearish.score == pytest.approx(-0.4)
    flat = oi_analyzer().analyze(25001, 1000, 1100, 500, NOW, [past])
    assert flat.status == FactorStatus.DISABLED and flat.weight == 0 and flat.bias == FactorBias.NEUTRAL
    assert oi_analyzer().analyze(25050, 1000, 1100, 500, NOW, []).status == FactorStatus.UNAVAILABLE


# ── Pre-market half-life ─────────────────────────────────────────────────────

def live_premarket(score=1.0, status=FactorStatus.ACTIVE):
    factor = B.build("Pre-Market Bias", score, 0.22, "live", FactorCluster.CONTEXT)
    return factor.model_copy(update={"status": status})


@pytest.mark.parametrize("clock, expected", [
    ((9, 0), 1.0), ((9, 15), 1.0), ((10, 45), 0.5), ((12, 15), 0.25),
])
def test_premarket_half_life_decay(clock, expected):
    analyzer = PremarketHalfLifeAnalyzer(B, 0.22, 90)
    assert analyzer.decay(IST.localize(datetime(2026, 11, 13, *clock))) == pytest.approx(expected)


def test_premarket_v2_weight_and_zero_on_wait_or_no_trade():
    analyzer = PremarketHalfLifeAnalyzer(B, 0.22, 90)
    at_half = IST.localize(datetime(2026, 11, 13, 10, 45))
    active = analyzer.analyze(live_premarket(0.6), "WATCH", at_half)
    assert active.name == PREMARKET_V2_NAME and active.score == 0.6 and active.weight == pytest.approx(0.11)
    for action in ("WAIT", "NO_TRADE"):
        zero = analyzer.analyze(live_premarket(0.6), action, at_half)
        assert zero.status == FactorStatus.DISABLED and zero.weight == 0 and zero.score == 0
    assert analyzer.analyze(None, "WATCH", at_half).status == FactorStatus.UNAVAILABLE
    unavailable_live = live_premarket(0.0, FactorStatus.UNAVAILABLE)
    assert analyzer.analyze(unavailable_live, "WATCH", at_half).status == FactorStatus.UNAVAILABLE
    with pytest.raises(ValueError):
        PremarketHalfLifeAnalyzer(B, 0.22, 0)


# ── IV rank gate ─────────────────────────────────────────────────────────────

def daily(n, start=10.0, step=1.0, end_day=date(2026, 11, 12)):
    return [DailyAtmIv(session_date=end_day - timedelta(days=n - i), atm_iv=start + i * step,
                       expiry=EXPIRY, captured_at=NOW) for i in range(n)]


def test_iv_gate_off_until_min_sessions():
    gate = IvRankGateEvaluator(lookback_sessions=60, min_sessions=20, block_at=80)
    assert gate.evaluate(None, daily(30), NOW.date()).status == IvRankGateStatus.OFF
    off = gate.evaluate(15.0, daily(19), NOW.date())
    assert off.status == IvRankGateStatus.OFF and off.sessions == 19 and off.iv_rank is None
    assert gate.evaluate(15.0, daily(20), NOW.date()).status != IvRankGateStatus.OFF


def test_iv_gate_block_threshold_inclusive_and_today_excluded():
    gate = IvRankGateEvaluator(lookback_sessions=60, min_sessions=20, block_at=80)
    history = daily(20, start=10.0, step=0.0)                      # flat 10
    history.append(DailyAtmIv(session_date=NOW.date(), atm_iv=99.0, expiry=EXPIRY, captured_at=NOW))
    history[0] = history[0].model_copy(update={"atm_iv": 20.0})    # range 10..20
    at_80 = gate.evaluate(18.0, history, NOW.date())               # (18-10)/10 = 80
    below = gate.evaluate(17.9, history, NOW.date())
    assert at_80.status == IvRankGateStatus.BLOCK_BUYING and at_80.iv_rank == 80.0
    assert below.status == IvRankGateStatus.PASS
    assert at_80.sessions == 20                                    # today's 99.0 not counted


def test_iv_gate_flat_history_is_mid_rank_and_lookback_truncates():
    gate = IvRankGateEvaluator(lookback_sessions=20, min_sessions=20, block_at=80)
    flat = gate.evaluate(10.0, daily(25, start=10.0, step=0.0), NOW.date())
    assert flat.iv_rank == 50.0 and flat.status == IvRankGateStatus.PASS
    assert gate.evaluate(30.0, daily(40), NOW.date()).sessions == 20


def test_daily_atm_iv_series_uses_last_reading_of_nearest_live_expiry():
    day1 = IST.localize(datetime(2026, 11, 11, 10, 0))
    day2 = IST.localize(datetime(2026, 11, 12, 10, 0))
    points = [
        point(0, iv=11.0, at=day1),
        point(0, iv=12.0, at=day1 + timedelta(hours=5)),                         # last of day 1
        point(0, iv=50.0, at=day1 + timedelta(hours=6), expiry=date(2026, 11, 24)),  # farther expiry
        point(0, iv=None, at=day2),
        point(0, iv=13.0, at=day2 + timedelta(hours=1)),
        point(0, iv=99.0, at=day2 + timedelta(hours=2), expiry=date(2026, 11, 10)),  # already expired
    ]
    series = daily_atm_iv_series(points)
    assert [(d.session_date, d.atm_iv) for d in series] == [(date(2026, 11, 11), 12.0), (date(2026, 11, 12), 13.0)]


# ── futures VWAP / RVOL ──────────────────────────────────────────────────────

def bars(day: date, start=(9, 15), n=6, volume=100.0, step=1.0, base=25000.0, up=True):
    t0 = IST.localize(datetime(day.year, day.month, day.day, *start))
    out = []
    for i in range(n):
        price = base + i * step
        o, c = (price, price + 0.5) if up else (price + 0.5, price)
        out.append(Candle(time=int((t0 + timedelta(minutes=5 * i)).timestamp()), open=o,
                          high=max(o, c) + 1, low=min(o, c) - 1, close=c, volume=volume))
    return out


def fva(**overrides):
    params = dict(vwap_weight=0.10, rvol_weight=0.05, min_session_bars=3, atr_period=4,
                  rvol_lookback_sessions=5, rvol_min_prior_sessions=3)
    params.update(overrides)
    return FuturesVolumeAnalyzer(B, **params)


TODAY = date(2026, 11, 13)
NOW_0945 = IST.localize(datetime(2026, 11, 13, 9, 45))   # bars 09:15..09:40 complete = 6


def test_futures_unavailable_without_candles_or_enough_bars():
    for candles in (None, []):
        assert {f.status for f in fva().analyze(candles, NOW_0945, "FUT")} == {FactorStatus.UNAVAILABLE}
    two = fva().analyze(bars(TODAY, n=2), NOW_0945, "FUT")
    assert all(f.status == FactorStatus.UNAVAILABLE and "Only 2" in f.detail for f in two)


def test_futures_completeness_gap_zero_volume_late_open():
    gap = bars(TODAY, n=6)
    del gap[3]
    assert "Gap" in fva().analyze(gap, NOW_0945, "FUT")[0].detail
    zero = bars(TODAY, n=6)
    zero[2] = zero[2].model_copy(update={"volume": 0})
    assert "zero volume" in fva().analyze(zero, NOW_0945, "FUT")[0].detail
    late = bars(TODAY, start=(9, 20), n=5)
    assert "not 09:15" in fva().analyze(late, NOW_0945, "FUT")[0].detail


def test_futures_vwap_excludes_incomplete_and_post_close_bars():
    candles = bars(TODAY, n=7)          # 7th bar (09:45) still forming at 09:45 → excluded
    vwap = fva().analyze(candles, NOW_0945, "FUT")[0]
    assert vwap.name == FUTURES_VWAP_NAME and vwap.status == FactorStatus.ACTIVE and "6 bars" in vwap.detail
    late = bars(TODAY, start=(15, 30), n=2)
    full_day_now = IST.localize(datetime(2026, 11, 13, 16, 0))
    day = bars(TODAY, n=75) + late
    assert "75 bars" in fva().analyze(day, full_day_now, "FUT")[0].detail


def test_futures_vwap_value():
    candles = bars(TODAY, n=6, step=2.0)          # closes 25000.5, 25002.5, ... rising, equal volume
    vwap = fva().analyze(candles, NOW_0945, "FUT")[0]
    typical = [((c.high + c.low + c.close) / 3) for c in candles]
    expected_vwap = sum(typical) / len(typical)
    assert f"VWAP {expected_vwap:.2f}" in vwap.detail
    assert vwap.score > 0 and vwap.bias == FactorBias.BULLISH


def prior_days_with_bar_at_0940(volumes):
    out = []
    for offset, volume in enumerate(volumes, start=1):
        day = TODAY - timedelta(days=offset)
        out += bars(day, n=6, volume=volume)
    return out


def test_futures_rvol_needs_min_prior_sessions():
    candles = prior_days_with_bar_at_0940([100, 100]) + bars(TODAY, n=6, volume=200)
    rvol = fva().analyze(candles, NOW_0945, "FUT")[1]
    assert rvol.name == FUTURES_RVOL_NAME and rvol.status == FactorStatus.UNAVAILABLE


def test_futures_rvol_confirms_direction_only_above_average():
    prior = prior_days_with_bar_at_0940([100, 100, 100])
    up = fva().analyze(prior + bars(TODAY, n=6, volume=150), NOW_0945, "FUT")[1]
    assert up.status == FactorStatus.ACTIVE and up.score == pytest.approx(0.5)
    down = fva().analyze(prior + bars(TODAY, n=6, volume=400, up=False), NOW_0945, "FUT")[1]
    assert down.score == -1.0                          # RVOL 4.0 clamps to -1
    average = fva().analyze(prior + bars(TODAY, n=6, volume=100), NOW_0945, "FUT")[1]
    assert average.status == FactorStatus.DISABLED and average.weight == 0   # RVOL exactly 1.0


def test_futures_rvol_skips_special_sessions():
    prior = prior_days_with_bar_at_0940([100, 100, 100])
    muhurat_day = TODAY - timedelta(days=4)
    muhurat = bars(muhurat_day, start=(9, 40), n=1, volume=10_000)   # session not opening 09:15
    rvol = fva().analyze(prior + muhurat + bars(TODAY, n=6, volume=150), NOW_0945, "FUT")[1]
    assert "3-session" in rvol.detail and rvol.score == pytest.approx(0.5)


# ── composition ──────────────────────────────────────────────────────────────

CONFIG = ShadowV2Config(
    version="v2.0", pcr_change_window_minutes=15, pcr_change_tolerance_minutes=4, pcr_change_full_scale=0.10,
    premarket_half_life_minutes=90, oi_buildup_weight=0.07, oi_buildup_window_minutes=15,
    oi_buildup_tolerance_minutes=4, oi_buildup_min_oi_change_pct=1.0, oi_buildup_min_price_change_pct=0.05,
    oi_buildup_full_scale_pct=5.0, futures_min_session_bars=3, futures_atr_period=4,
    futures_rvol_lookback_sessions=5, futures_rvol_min_prior_sessions=3, iv_rank_lookback_sessions=60,
    iv_rank_min_sessions=20, iv_rank_block_buying_at=80.0,
)


def live_prediction(adx_multiplier=1.0, atm_iv=14.0):
    factors = [
        B.build("AI Agents", 0.5, 0.12, "agents", FactorCluster.CONTEXT),
        B.build("Put-Call Ratio", -1.0, 0.10, "level", FactorCluster.OPTIONS),
        B.disabled("ΔOI Dynamics", 0.9, "old", FactorCluster.OPTIONS),
        B.disabled("IV Rank", 0.5, "old", FactorCluster.REGIME),
        B.build("EMA 20 Trend (5m)", 1.0, 0.08, "ema", FactorCluster.TREND),
        B.unavailable("VWAP (5m)", "index has no volume", FactorCluster.LEVELS),
        B.unavailable("Relative Volume (5m)", "index has no volume", FactorCluster.LEVELS),
        B.build("Pre-Market Bias", 1.0, 0.22, "pm", FactorCluster.CONTEXT),
    ]
    return OptionPrediction.model_construct(
        underlying="NIFTY", expiry=EXPIRY, spot=25050.0, generated_at=NOW, factors=factors,
        premarket_action="WATCH", direction=PredictionDirection.CALL, score=0.4,
        regime=RegimeSnapshot(label=RegimeLabel.TRENDING if hasattr(RegimeLabel, "TRENDING") else list(RegimeLabel)[0],
                              adx=30, vix=15, vix_change_pct=0, atm_iv=atm_iv, adx_multiplier=adx_multiplier),
        shadow=ShadowFeatures(
            chain=ChainShadowFeatures(strike_window=500, near_call_oi=1000, near_put_oi=1100,
                                      near_spot_pcr=1.1, atm_iv=atm_iv, iv_skew_25d=None, gex_per_1pct=None,
                                      quotes_with_iv=0, quotes_total=0),
            futures=None,
        ),
    )


def scorer():
    return build_shadow_scorer_v2(CONFIG, B, live_weight_budget=1.0)


def test_compose_replaces_rebuilt_factors_and_keeps_the_rest():
    prediction = live_prediction()
    inputs = ShadowV2Inputs(chain_history=[point(15, pcr=1.0, call=1000, put=1000, spot=25000)])
    v2 = scorer().compose(prediction, inputs)
    names = [f.name for f in v2.factors]
    assert names == [
        "AI Agents", "Δ Near-Spot PCR (15m)", "ΔOI Buildup (15m)", "EMA 20 Trend (5m)",
        FUTURES_VWAP_NAME, FUTURES_RVOL_NAME, PREMARKET_V2_NAME,
    ]
    assert "IV Rank" not in names
    assert [f.name for f in prediction.factors][1] == "Put-Call Ratio"     # live list untouched
    by_name = {f.name: f for f in v2.factors}
    assert by_name["Δ Near-Spot PCR (15m)"].score == 1.0                    # +0.10 PCR → +1
    assert by_name["ΔOI Buildup (15m)"].status == FactorStatus.ACTIVE
    assert v2.version == "v2.0" and v2.direction == PredictionDirection.CALL and v2.error is None
    assert v2.coverage == pytest.approx(round((0.12 + 0.10 + 0.07 + 0.08 + 0.22 * 0.5 ** (105 / 90)) / 1.07, 3))


def test_compose_applies_adx_multiplier_and_iv_gate():
    inputs = ShadowV2Inputs(daily_atm_iv=daily(20, start=10.0, step=0.5))   # range 10..19.5
    damped = scorer().compose(live_prediction(adx_multiplier=0.5), inputs)
    assert damped.adjusted_score == pytest.approx(round(damped.raw_score * 0.5, 3))
    blocked = scorer().compose(live_prediction(atm_iv=30.0), inputs)
    assert blocked.iv_rank_gate.status == IvRankGateStatus.BLOCK_BUYING
    assert blocked.direction == PredictionDirection.NO_TRADE and blocked.gate == IV_RANK_GATE_REASON


@pytest.mark.asyncio
async def test_evaluate_never_raises_and_records_errors():
    class BrokenHistory:
        async def chain_points(self, *_):
            raise RuntimeError("db down")

    async def broken_futures(_):
        raise TimeoutError()

    result = await build_shadow_scorer_v2(
        CONFIG, B, 1.0, history=BrokenHistory(), futures_candles=broken_futures
    ).evaluate(live_prediction())
    assert result.error is None
    assert any("snapshot history unavailable" in n for n in result.notes)
    assert any("futures candles unavailable" in n for n in result.notes)

    crashed = await scorer().evaluate(object())        # compose cannot even read the prediction
    assert crashed.error is not None and crashed.direction == PredictionDirection.NO_TRADE


def test_live_factor_names_match_v2_replacement_slots():
    """Guards against a live rename silently leaving a v1 factor in the v2 score."""
    from schemas.prediction import ChainMetrics, IntradayIndicators
    from services.prediction.chain_factor_analyzer import ChainFactorAnalyzer
    from services.prediction.technical_factor_analyzer import TechnicalFactorAnalyzer
    from services.prediction.v2.shadow_scorer_v2 import ShadowScorerV2

    metrics = ChainMetrics(put_call_ratio=1, max_pain=25000, call_wall=25500, put_wall=24500,
                           total_call_oi=1, total_put_oi=1, iv_rank=50.0, near_spot_pcr=1.0)
    chain_names = [f.name for f in ChainFactorAnalyzer(B, 500, 3).analyze(metrics, 25000, EXPIRY, TODAY)]
    indicators = IntradayIndicators(price=1, rsi=50, macd_histogram=0, ema_20=1, atr=1, supertrend_direction=1)
    tech_names = [f.name for f in TechnicalFactorAnalyzer(B, "5m").analyze(indicators)]
    slots = {n: ShadowScorerV2._slot(n) for n in chain_names + tech_names + ["Pre-Market Bias"]}
    assert slots["Put-Call Ratio"] == "pcr" and slots["ΔOI Dynamics"] == "oi" and slots["IV Rank"] == "drop"
    assert slots["VWAP (5m)"] == "vwap" and slots["Relative Volume (5m)"] == "rvol"
    assert slots["Pre-Market Bias"] == "premarket"
