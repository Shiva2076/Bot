from datetime import date, datetime, timezone

import pytz

from schemas.options import OptionUnderlying
from schemas.prediction import (
    ClusterScore,
    FactorBias,
    FactorCluster,
    FactorStatus,
    GateReason,
    IntradayIndicators,
    PredictionFactor,
)
from schemas.premarket import RecommendedAction
from schemas.trading import Tick
from services.prediction.adx_regime_multiplier import AdxRegimeMultiplier
from services.prediction.agent_factor_analyzer import AgentFactorAnalyzer
from services.prediction.chain_factor_analyzer import ChainFactorAnalyzer
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.factor_contribution_annotator import FactorContributionAnnotator
from services.prediction.prediction_market_gate import PredictionMarketGate
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.prediction_wait_gate import PredictionWaitGate
from services.prediction.prediction_weight_budget import PredictionWeightBudget
from services.premarket.trading_calendar import TradingCalendar
from schemas.prediction import AgentConsensus, ChainMetrics


IST = pytz.timezone("Asia/Kolkata")


def _wait_gate(
    min_coverage: float = 0.5,
    min_signal: float = 50.0,
) -> PredictionWaitGate:
    return PredictionWaitGate(min_coverage, PredictionWeightBudget(0.12), 0.15, min_signal)


def _factor(name: str, score: float, weight: float, cluster: FactorCluster) -> PredictionFactor:
    return PredictionFactor(
        name=name,
        bias=FactorBias.BULLISH if score > 0 else FactorBias.BEARISH if score < 0 else FactorBias.NEUTRAL,
        score=score,
        weight=weight,
        detail="t",
        cluster=cluster,
        status=FactorStatus.ACTIVE,
    )


def _indicators(price: float, ema: float) -> IntradayIndicators:
    return IntradayIndicators(
        price=price, rsi=50, macd_histogram=0, ema_20=ema, atr=10, supertrend_direction=1
    )


def test_market_closed_gate():
    calendar = TradingCalendar(set())
    gate = PredictionMarketGate(calendar, 30.0)
    now = IST.localize(datetime(2026, 10, 21, 18, 0)).astimezone(timezone.utc)
    tick = Tick(
        symbol="^NSEI", ltp=1, prev_close=1, change=0, change_pct=0,
        timestamp=now, provider="TEST", fetched_at=now, exchange_timestamp=now,
    )
    result = gate.evaluate(now, [tick])
    assert result.gate_reason == GateReason.MARKET_CLOSED
    assert result.blocks_action


def test_stale_quote_gate_during_regular_hours():
    calendar = TradingCalendar(set())
    gate = PredictionMarketGate(calendar, 30.0)
    now = IST.localize(datetime(2026, 10, 21, 10, 30)).astimezone(timezone.utc)
    from datetime import timedelta
    exchange = now - timedelta(seconds=45)
    tick = Tick(
        symbol="^NSEI", ltp=1, prev_close=1, change=0, change_pct=0,
        timestamp=exchange, provider="TEST", fetched_at=now, exchange_timestamp=exchange,
    )
    result = gate.evaluate(now, [tick])
    assert result.gate_reason == GateReason.STALE_DATA


def test_wait_mtf_conflict():
    gate = _wait_gate()
    assert gate.mtf_conflict(_indicators(110, 100), _indicators(90, 100)) is True
    assert gate.mtf_conflict(_indicators(110, 100), _indicators(110, 100)) is False


def test_wait_cluster_disagreement():
    gate = _wait_gate()
    scores = {
        FactorCluster.TREND: ClusterScore(score=0.5, active_factors=1, total_factors=1),
        FactorCluster.LEVELS: ClusterScore(score=-0.4, active_factors=1, total_factors=1),
        FactorCluster.OPTIONS: ClusterScore(score=None, active_factors=0, total_factors=0),
        FactorCluster.FUTURES_FLOW: ClusterScore(score=None, active_factors=0, total_factors=0),
        FactorCluster.CONTEXT: ClusterScore(score=None, active_factors=0, total_factors=0),
        FactorCluster.AGENTS: ClusterScore(score=None, active_factors=0, total_factors=0),
        FactorCluster.REGIME: ClusterScore(score=None, active_factors=0, total_factors=0),
    }
    assert gate.cluster_disagreement(scores) is True


def test_wait_low_coverage_and_premarket():
    gate = _wait_gate(min_coverage=0.5)
    factors = [_factor("A", 1.0, 0.2, FactorCluster.TREND)]
    scores = {c: ClusterScore(score=None, active_factors=0, total_factors=0) for c in FactorCluster}
    scores[FactorCluster.TREND] = ClusterScore(score=1.0, active_factors=1, total_factors=1)
    reason = gate.evaluate(
        factors, scores, _indicators(100, 100), _indicators(100, 100),
        RecommendedAction.WAIT, signal_score=80.0, invalid_data=False,
    )
    assert reason == GateReason.PREMARKET_WAIT
    reason2 = gate.evaluate(
        factors, scores, _indicators(100, 100), _indicators(100, 100),
        RecommendedAction.WATCH, signal_score=80.0, invalid_data=False,
    )
    assert reason2 == GateReason.LOW_COVERAGE


def test_wait_low_signal_score():
    gate = _wait_gate(min_coverage=0.1, min_signal=50.0)
    factors = [_factor("A", 1.0, 0.8, FactorCluster.TREND)]
    scores = {c: ClusterScore(score=None, active_factors=0, total_factors=0) for c in FactorCluster}
    scores[FactorCluster.TREND] = ClusterScore(score=1.0, active_factors=1, total_factors=1)
    reason = gate.evaluate(
        factors, scores, _indicators(100, 100), _indicators(100, 100),
        RecommendedAction.WATCH, signal_score=49.9, invalid_data=False,
    )
    assert reason == GateReason.LOW_SIGNAL_SCORE


def test_agent_score_is_direction_times_confidence():
    f = AgentFactorAnalyzer(PredictionFactorBuilder(), 0.12).analyze(
        AgentConsensus(action="BUY", confidence=60.0, bullish_agents=3, bearish_agents=1, reasons=[])
    )
    assert f.score == 0.6
    assert f.weight == 0.12


def test_adx_multiplier_non_directional():
    m = AdxRegimeMultiplier(25.0, 20.0, 0.7, 1.0)
    assert m.multiplier(12.0) == 0.7
    assert m.multiplier(30.0) == 1.0


def test_signal_score_formula():
    scorer = PredictionScorer()
    assert scorer.signal_score(0.4, 1.0) == 70.0
    assert scorer.signal_score(0.4, 0.5) == 35.0


def test_contribution_annotator():
    factors = [
        _factor("A", 1.0, 0.2, FactorCluster.TREND),
        _factor("B", -1.0, 0.2, FactorCluster.LEVELS),
    ]
    out = FactorContributionAnnotator().annotate(factors)
    assert out[0].contribution_pct == 50.0
    assert out[1].contribution_pct == -50.0


def test_near_spot_pcr_and_max_pain_dte():
    analyzer = ChainFactorAnalyzer(PredictionFactorBuilder(), 500.0, 3)
    metrics = ChainMetrics(
        put_call_ratio=0.5, max_pain=25100.0, call_wall=25200.0, put_wall=24800.0,
        total_call_oi=1e6, total_put_oi=1e6, near_spot_pcr=1.2, strike_window=500.0,
    )
    factors = analyzer.analyze(metrics, 25000.0, date(2026, 10, 30), date(2026, 10, 27))
    pcr = next(f for f in factors if f.name == "Put-Call Ratio")
    assert pcr.status == FactorStatus.ACTIVE
    assert "Near-spot PCR 1.20" in pcr.detail
    mp = next(f for f in factors if f.name == "Max Pain")
    assert mp.status == FactorStatus.DISABLED
