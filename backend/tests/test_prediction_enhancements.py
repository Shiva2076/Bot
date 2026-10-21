"""
Tests for all Phase 1-3 prediction enhancements:
  - VWAP, RVOL, Initial Balance, ADX factors (TechnicalFactorAnalyzer)
  - ΔOI dynamics and IV Rank (ChainMetricsCalculator + ChainFactorAnalyzer)
  - India VIX factor (VixFactorAnalyzer)
  - Breadth factor (BreadthFactorAnalyzer)
  - MTF alignment (MTFFactorAnalyzer)
  - Time context (TimeContextAnalyzer)
  - RVOL + IB in technical analysis engine
"""
import pytest
from datetime import datetime, time as dtime, date
from unittest.mock import MagicMock

import pandas as pd
import numpy as np

# ── Engine ───────────────────────────────────────────────────────────────────

from engines.technical_analysis import (
    compute_rvol,
    run_full_analysis,
)


def _make_ohlcv(n: int = 50, base_price: float = 100.0) -> pd.DataFrame:
    """Create a synthetic OHLCV dataframe."""
    np.random.seed(42)
    closes = base_price + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open":   closes - 0.1,
        "high":   closes + 0.5,
        "low":    closes - 0.5,
        "close":  closes,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })
    return df


class TestComputeRvol:
    def test_returns_ratio(self):
        df = _make_ohlcv(50)
        rvol = compute_rvol(df, window=20)
        assert rvol is not None
        assert rvol > 0

    def test_returns_none_when_insufficient_data(self):
        df = _make_ohlcv(10)
        assert compute_rvol(df, window=20) is None

    def test_high_volume_gives_high_rvol(self):
        df = _make_ohlcv(30)
        df.loc[df.index[-1], "volume"] = df["volume"].mean() * 10
        rvol = compute_rvol(df, window=20)
        assert rvol is not None and rvol > 2.0


class TestRunFullAnalysisExtended:
    def test_vwap_in_output(self):
        df = _make_ohlcv(50)
        result = run_full_analysis(df)
        assert "vwap" in result
        assert result["vwap"] > 0

    def test_rvol_in_output(self):
        df = _make_ohlcv(50)
        result = run_full_analysis(df)
        assert "rvol" in result

    def test_no_engine_initial_balance(self):
        result = run_full_analysis(_make_ohlcv(50))
        assert "ib_high" not in result


# ── TechnicalFactorAnalyzer ──────────────────────────────────────────────────

from schemas.prediction import FactorStatus, IntradayIndicators, SessionRange, SessionRangeKind
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.technical_factor_analyzer import TechnicalFactorAnalyzer


def _ib(high: float, low: float) -> SessionRange:
    return SessionRange(kind=SessionRangeKind.INITIAL_BALANCE, minutes=60, high=high, low=low)


def _make_indicators(**overrides) -> IntradayIndicators:
    defaults = dict(
        price=100.0, rsi=55.0, macd_histogram=0.5,
        ema_20=98.0, atr=1.5, supertrend_direction=1,
        vwap=99.0, volume_ratio=1.2, rvol=1.3,
        session_range=_ib(102.0, 97.0), adx=28.0,
    )
    defaults.update(overrides)
    return IntradayIndicators(**defaults)


class TestTechnicalFactorAnalyzer:
    def setup_method(self):
        self.builder = PredictionFactorBuilder()
        self.analyzer = TechnicalFactorAnalyzer(self.builder, "5m")

    def test_returns_expected_factor_names(self):
        indicators = _make_indicators()
        factors = self.analyzer.analyze(indicators)
        names = {f.name for f in factors}
        assert "VWAP (5m)" in names
        assert "Relative Volume (5m)" in names
        assert "Initial Balance (5m)" in names
        assert not any("ADX" in n for n in names)

    def test_vwap_above_gives_positive_score(self):
        indicators = _make_indicators(price=105.0, vwap=100.0, atr=2.0)
        factors = self.analyzer.analyze(indicators)
        vwap_f = next(f for f in factors if "VWAP" in f.name)
        assert vwap_f.score > 0

    def test_vwap_below_gives_negative_score(self):
        indicators = _make_indicators(price=95.0, vwap=100.0, atr=2.0)
        factors = self.analyzer.analyze(indicators)
        vwap_f = next(f for f in factors if "VWAP" in f.name)
        assert vwap_f.score < 0

    def test_high_rvol_positive(self):
        indicators = _make_indicators(rvol=2.5)
        factors = self.analyzer.analyze(indicators)
        rvol_f = next(f for f in factors if "Relative Volume" in f.name)
        assert rvol_f.score > 0

    def test_low_rvol_negative(self):
        indicators = _make_indicators(rvol=0.3)
        factors = self.analyzer.analyze(indicators)
        rvol_f = next(f for f in factors if "Relative Volume" in f.name)
        assert rvol_f.score < 0

    def test_price_above_ib_high_bullish(self):
        indicators = _make_indicators(price=104.0, session_range=_ib(102.0, 97.0))
        factors = self.analyzer.analyze(indicators)
        ib_f = next(f for f in factors if "Initial Balance" in f.name)
        assert ib_f.score > 0

    def test_price_below_ib_low_bearish(self):
        indicators = _make_indicators(price=95.0, session_range=_ib(102.0, 97.0))
        factors = self.analyzer.analyze(indicators)
        ib_f = next(f for f in factors if "Initial Balance" in f.name)
        assert ib_f.score < 0

    def test_adx_no_longer_a_directional_factor(self):
        factors = self.analyzer.analyze(_make_indicators(adx=35.0))
        assert not any("ADX" in f.name for f in factors)

    def test_no_session_range_is_unavailable_with_zero_weight(self):
        factors = self.analyzer.analyze(_make_indicators(session_range=None))
        ib_f = next(f for f in factors if "Initial Balance" in f.name)
        assert ib_f.status == FactorStatus.UNAVAILABLE
        assert ib_f.weight == 0.0

    def test_missing_volume_zeroes_vwap_and_rvol(self):
        factors = self.analyzer.analyze(_make_indicators(vwap=None, rvol=None, volume_ratio=None))
        for name in ("VWAP (5m)", "Relative Volume (5m)"):
            factor = next(f for f in factors if f.name == name)
            assert factor.status == FactorStatus.UNAVAILABLE
            assert factor.weight == 0.0 and factor.score == 0.0

    def test_no_adx_omits_adx_factor(self):
        indicators = _make_indicators(adx=None)
        factors = self.analyzer.analyze(indicators)
        assert not any("ADX" in f.name for f in factors)


# ── ChainMetricsCalculator ───────────────────────────────────────────────────

from schemas.options import (
    OptionChain, OptionChainRow, OptionQuote, OptionType, OptionUnderlying
)
from services.prediction.chain_metrics_calculator import ChainMetricsCalculator
from services.prediction.strike_window_policy import StrikeWindowPolicy


def _make_quote(oi: float, ltp: float = 10.0, iv: float = None) -> OptionQuote:
    return OptionQuote(
        symbol="TEST", display_name="TEST", ltp=ltp,
        change=0.0, change_pct=0.0, open_interest=oi,
        volume=1000, bid=None, ask=None, implied_volatility=iv,
    )


def _make_chain(call_ois, put_ois, spot=100.0) -> OptionChain:
    rows = [
        OptionChainRow(
            strike=100.0 + i * 50,
            call=_make_quote(c_oi),
            put=_make_quote(p_oi),
        )
        for i, (c_oi, p_oi) in enumerate(zip(call_ois, put_ois))
    ]
    atm_strike = min(rows, key=lambda r: abs(r.strike - spot)).strike
    return OptionChain(
        underlying=OptionUnderlying.NIFTY,
        expiry=date(2026, 10, 30),
        spot=spot,
        atm_strike=atm_strike,
        lot_size=50,
        rows=rows,
    )


class TestChainMetricsCalculatorDeltaOI:
    def setup_method(self):
        self.calc = ChainMetricsCalculator(StrikeWindowPolicy({OptionUnderlying.NIFTY: 500.0}))

    def test_first_snapshot_oi_change_is_zero(self):
        chain = _make_chain([1000, 2000, 3000], [3000, 2000, 1000])
        metrics = self.calc.calculate(chain)
        assert metrics.call_oi_change == 0.0
        assert metrics.put_oi_change == 0.0
        assert metrics.oi_interpretation == "STABLE"

    def test_second_snapshot_shows_delta(self):
        chain1 = _make_chain([1000, 2000, 3000], [3000, 2000, 1000])
        self.calc.calculate(chain1)
        # Increase call OI significantly
        chain2 = _make_chain([2000, 3000, 4000], [3000, 2000, 1000])
        # Force cache key match by using same underlying/expiry
        metrics = self.calc.calculate(chain2)
        assert metrics.call_oi_change > 0

    def test_iv_rank_neutral_when_single_reading(self):
        chain = _make_chain([1000, 2000], [2000, 1000])
        # Inject IV into ATM row
        chain.rows[0].call.implied_volatility = 20.0
        metrics = self.calc.calculate(chain)
        # With a single reading, lo == hi → 50.0
        if metrics.iv_rank is not None:
            assert metrics.iv_rank == 50.0


# ── ChainFactorAnalyzer ──────────────────────────────────────────────────────

from schemas.prediction import ChainMetrics
from services.prediction.chain_factor_analyzer import ChainFactorAnalyzer


def _make_metrics(**kw) -> ChainMetrics:
    defaults = dict(
        put_call_ratio=1.1, max_pain=100.0, call_wall=110.0,
        put_wall=90.0, total_call_oi=100000.0, total_put_oi=110000.0,
        call_oi_change=5000.0, put_oi_change=-2000.0,
        oi_interpretation="CALL_LONG_BUILDUP", atm_iv=18.0, iv_rank=25.0,
        near_spot_pcr=1.1, strike_window=500.0,
    )
    defaults.update(kw)
    return ChainMetrics(**defaults)


class TestChainFactorAnalyzerNew:
    def setup_method(self):
        self.analyzer = ChainFactorAnalyzer(
            PredictionFactorBuilder(), oi_wall_proximity_points=500.0, max_pain_zero_dte=3
        )
        self.expiry = date(2026, 10, 27)
        self.today = date(2026, 10, 27)

    def test_oi_delta_factor_present(self):
        metrics = _make_metrics()
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        names = {f.name for f in factors}
        assert "ΔOI Dynamics" in names

    def test_iv_rank_factor_present(self):
        metrics = _make_metrics()
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        names = {f.name for f in factors}
        assert "IV Rank" in names

    def test_call_buildup_gives_positive_oi_delta(self):
        metrics = _make_metrics(oi_interpretation="CALL_LONG_BUILDUP",
                                call_oi_change=10000, put_oi_change=0)
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        oi_f = next(f for f in factors if f.name == "ΔOI Dynamics")
        assert oi_f.score > 0

    def test_put_buildup_gives_negative_oi_delta(self):
        metrics = _make_metrics(oi_interpretation="PUT_LONG_BUILDUP",
                                call_oi_change=0, put_oi_change=10000)
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        oi_f = next(f for f in factors if f.name == "ΔOI Dynamics")
        assert oi_f.score < 0

    def test_low_iv_rank_positive_score(self):
        metrics = _make_metrics(iv_rank=10.0)
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        iv_f = next(f for f in factors if f.name == "IV Rank")
        assert iv_f.score > 0

    def test_high_iv_rank_negative_score(self):
        metrics = _make_metrics(iv_rank=90.0)
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        iv_f = next(f for f in factors if f.name == "IV Rank")
        assert iv_f.score < 0

    def test_no_iv_rank_omits_factor(self):
        metrics = _make_metrics(iv_rank=None)
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        assert not any(f.name == "IV Rank" for f in factors)

    def test_oi_delta_and_iv_rank_disabled_with_zero_weight(self):
        factors = self.analyzer.analyze(_make_metrics(), 100.0, self.expiry, self.today)
        for name in ("ΔOI Dynamics", "IV Rank"):
            factor = next(f for f in factors if f.name == name)
            assert factor.status == FactorStatus.DISABLED
            assert factor.weight == 0.0

    def test_oi_wall_far_away_is_disabled(self):
        metrics = _make_metrics(put_wall=90.0, call_wall=110.0)
        factors = self.analyzer.analyze(metrics, 100.0, self.expiry, self.today)
        # walls are within 500 of spot 100 — active. Far case:
        far = _make_metrics(put_wall=20000.0, call_wall=21000.0)
        factors_far = self.analyzer.analyze(far, 25000.0, self.expiry, self.today)
        wall = next(f for f in factors_far if f.name == "OI Support / Resistance")
        assert wall.status == FactorStatus.DISABLED and wall.weight == 0.0

    def test_max_pain_weight_scales_with_dte(self):
        metrics = _make_metrics(near_spot_pcr=1.1)
        near = self.analyzer.analyze(metrics, 100.0, date(2026, 10, 27), date(2026, 10, 27))
        far = self.analyzer.analyze(metrics, 100.0, date(2026, 10, 30), date(2026, 10, 27))
        mp_near = next(f for f in near if f.name == "Max Pain")
        mp_far = next(f for f in far if f.name == "Max Pain")
        assert mp_near.weight > 0
        assert mp_far.status == FactorStatus.DISABLED


# ── VixFactorAnalyzer ────────────────────────────────────────────────────────

from schemas.premarket import IndiaVixSnapshot, VolatilityBand
from services.prediction.vix_factor_analyzer import VixFactorAnalyzer


def _make_vix(value: float, change_pct: float = 0.0, band: VolatilityBand = VolatilityBand.MODERATE):
    return IndiaVixSnapshot(
        available=True, value=value, change_pct=change_pct,
        band=band, trend="FLAT", source="test",
    )


class TestVixFactorAnalyzer:
    def setup_method(self):
        self.analyzer = VixFactorAnalyzer(PredictionFactorBuilder())

    def test_low_vix_positive_score(self):
        f = self.analyzer.analyze(_make_vix(10.0, band=VolatilityBand.LOW))
        assert f.score > 0

    def test_high_vix_negative_score(self):
        f = self.analyzer.analyze(_make_vix(22.0, band=VolatilityBand.HIGH))
        assert f.score < 0

    def test_extreme_vix_max_negative(self):
        # 70% level (-1.0) + 30% flat trend (0) => -0.7 after clamp rounding
        f = self.analyzer.analyze(_make_vix(28.0, band=VolatilityBand.HIGH))
        assert f.score == -0.7

    def test_rising_vix_more_negative_than_flat(self):
        flat = self.analyzer.analyze(_make_vix(18.0, change_pct=0.0))
        rising = self.analyzer.analyze(_make_vix(18.0, change_pct=5.0))
        assert rising.score < flat.score

    def test_unavailable_vix_neutral(self):
        snap = IndiaVixSnapshot(available=False)
        f = self.analyzer.analyze(snap)
        assert f.score == 0.0
        assert f.weight == 0.0 and f.status == FactorStatus.UNAVAILABLE


# ── BreadthFactorAnalyzer ────────────────────────────────────────────────────

from schemas.premarket import BreadthSnapshot
from services.prediction.breadth_factor_analyzer import BreadthFactorAnalyzer


class TestBreadthFactorAnalyzer:
    def setup_method(self):
        self.analyzer = BreadthFactorAnalyzer(PredictionFactorBuilder())

    def test_strong_advance_positive(self):
        snap = BreadthSnapshot(available=True, advancing=40, declining=10,
                               unchanged=0, advance_decline_ratio=4.0,
                               advancing_pct=80.0, session_label="INTRADAY")
        f = self.analyzer.analyze(snap)
        assert f.score > 0

    def test_strong_decline_negative(self):
        snap = BreadthSnapshot(available=True, advancing=10, declining=40,
                               unchanged=0, advance_decline_ratio=0.25,
                               advancing_pct=20.0, session_label="INTRADAY")
        f = self.analyzer.analyze(snap)
        assert f.score < 0

    def test_unavailable_neutral(self):
        snap = BreadthSnapshot(available=False)
        f = self.analyzer.analyze(snap)
        assert f.score == 0.0
        assert f.weight == 0.0 and f.status == FactorStatus.UNAVAILABLE


# ── MTFFactorAnalyzer ────────────────────────────────────────────────────────

from services.prediction.mtf_factor_analyzer import MTFFactorAnalyzer


class TestMTFFactorAnalyzer:
    def setup_method(self):
        self.analyzer = MTFFactorAnalyzer(PredictionFactorBuilder())

    def test_aligned_bullish_positive(self):
        ind5 = _make_indicators(price=105.0, ema_20=100.0, supertrend_direction=1)
        ind15 = _make_indicators(price=105.0, ema_20=100.0, supertrend_direction=1)
        f = self.analyzer.analyze(ind5, ind15)
        assert f is not None and f.score > 0.5

    def test_aligned_bearish_negative(self):
        ind5 = _make_indicators(price=95.0, ema_20=100.0, supertrend_direction=-1)
        ind15 = _make_indicators(price=95.0, ema_20=100.0, supertrend_direction=-1)
        f = self.analyzer.analyze(ind5, ind15)
        assert f is not None and f.score < -0.5

    def test_conflict_near_neutral(self):
        ind5 = _make_indicators(price=105.0, ema_20=100.0, supertrend_direction=1)
        ind15 = _make_indicators(price=95.0, ema_20=100.0, supertrend_direction=-1)
        f = self.analyzer.analyze(ind5, ind15)
        assert f is not None and abs(f.score) <= 0.15

    def test_none_15m_returns_none(self):
        ind5 = _make_indicators()
        f = self.analyzer.analyze(ind5, None)
        assert f is None


# ── TimeContextAnalyzer ──────────────────────────────────────────────────────

from services.prediction.time_context_analyzer import TimeContextAnalyzer
import pytz

IST = pytz.timezone("Asia/Kolkata")


class TestTimeContextAnalyzer:
    def setup_method(self):
        self.analyzer = TimeContextAnalyzer()

    EXPIRY = date(2026, 10, 20)

    def _now(self, h, m, day=20) -> datetime:
        return IST.localize(datetime(2026, 10, day, h, m, 0))

    def test_opening_has_low_modifier(self):
        ctx = self.analyzer.analyze(self.EXPIRY, self._now(9, 25, day=19))
        assert ctx.session == "OPENING"
        assert ctx.confidence_modifier < 0.80

    def test_mid_morning_full_modifier(self):
        ctx = self.analyzer.analyze(self.EXPIRY, self._now(10, 30, day=19))
        assert ctx.session == "MID_MORNING"
        assert ctx.confidence_modifier == 1.0

    def test_lull_has_reduced_modifier(self):
        ctx = self.analyzer.analyze(self.EXPIRY, self._now(12, 0, day=19))
        assert ctx.session == "MIDDAY_LULL"
        assert ctx.confidence_modifier < 1.0

    def test_pre_close_low_modifier(self):
        ctx = self.analyzer.analyze(self.EXPIRY, self._now(15, 0, day=19))
        assert ctx.session == "PRE_CLOSE"
        assert ctx.confidence_modifier <= 0.70

    def test_contract_expiry_date_is_expiry_day(self):
        ctx = self.analyzer.analyze(self.EXPIRY, self._now(10, 30, day=20))
        assert ctx.is_expiry_day is True

    def test_thursday_is_not_expiry_when_contract_expires_tuesday(self):
        ctx = self.analyzer.analyze(self.EXPIRY, self._now(10, 30, day=22))
        assert ctx.is_expiry_day is False

    def test_expiry_pre_close_lower_modifier(self):
        expiry_ctx = self.analyzer.analyze(self.EXPIRY, self._now(15, 0, day=20))
        normal_ctx = self.analyzer.analyze(self.EXPIRY, self._now(15, 0, day=19))
        assert expiry_ctx.confidence_modifier < normal_ctx.confidence_modifier
