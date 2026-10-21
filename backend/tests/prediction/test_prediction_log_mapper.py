from datetime import date, datetime, timezone

from schemas.options import OptionQuote, OptionType, OptionUnderlying
from schemas.prediction import (
    ChainMetrics,
    ChainShadowFeatures,
    ClusterScore,
    DataFreshness,
    FactorBias,
    FactorCluster,
    FactorStatus,
    GateReason,
    OptionPrediction,
    PredictionDirection,
    PredictionFactor,
    PremiumLevels,
    RegimeLabel,
    RegimeSnapshot,
    ShadowFeatures,
    SuggestedContract,
)
from services.prediction.prediction_log_mapper import PredictionLogMapper


def _prediction() -> OptionPrediction:
    return OptionPrediction(
        underlying=OptionUnderlying.NIFTY,
        expiry=date(2026, 10, 27),
        spot=25000.0,
        lot_size=65,
        direction=PredictionDirection.WAIT,
        score=0.4,
        raw_score=0.4,
        signal_score=48.0,
        confidence=48.0,
        time_modifier=0.7,
        coverage=0.62,
        gate_reason=GateReason.LOW_SIGNAL_SCORE,
        session_status="POST_CLOSE",
        data_freshness=DataFreshness.MARKET_CLOSED,
        quote_timestamps=[],
        contract=SuggestedContract(
            strike=25000.0,
            option_type=OptionType.CE,
            quote=OptionQuote(
                symbol="NIFTY27OCT2625000CE",
                display_name="NIFTY 25000 CE",
                ltp=100.0,
                change=1.0,
                change_pct=1.0,
                open_interest=1000.0,
                volume=500.0,
                bid=99.0,
                ask=101.0,
            ),
            levels=PremiumLevels(entry=101.0, stop_loss=80.0, target=140.0),
        ),
        metrics=ChainMetrics(
            put_call_ratio=1.1,
            max_pain=24900.0,
            call_wall=25200.0,
            put_wall=24800.0,
            total_call_oi=1_000_000.0,
            total_put_oi=1_100_000.0,
            near_spot_pcr=1.05,
            strike_window=500.0,
        ),
        factors=[
            PredictionFactor(
                name="EMA 20 Trend (5m)",
                bias=FactorBias.BULLISH,
                score=0.5,
                weight=0.1,
                detail="above",
                cluster=FactorCluster.TREND,
                status=FactorStatus.ACTIVE,
                contribution=0.5,
                contribution_pct=50.0,
                effective_weight=0.1,
            )
        ],
        generated_at=datetime(2026, 10, 20, 4, 0, tzinfo=timezone.utc),
        session_label="MID_MORNING",
        is_expiry_day=False,
        cluster_scores={FactorCluster.TREND: ClusterScore(score=0.5, active_factors=1, total_factors=1)},
        regime=RegimeSnapshot(
            label=RegimeLabel.TRENDING, adx=28.0, vix=13.0, vix_change_pct=-1.0, atm_iv=12.5, adx_multiplier=1.0
        ),
        shadow=ShadowFeatures(
            chain=ChainShadowFeatures(
                strike_window=500.0,
                near_call_oi=1000.0,
                near_put_oi=1200.0,
                near_spot_pcr=1.2,
                atm_iv=12.5,
                iv_skew_25d=1.5,
                gex_per_1pct=1000.0,
                quotes_with_iv=2,
                quotes_total=2,
            ),
            futures=None,
        ),
    )


def test_mapper_builds_create_payload():
    payload = PredictionLogMapper("v1.2_gates", "v1_data_fixes").to_create(_prediction())
    assert payload.scorer_version == "v1.2_gates"
    assert payload.data_version == "v1_data_fixes"
    assert payload.lot_size == 65
    assert payload.direction == PredictionDirection.WAIT
    assert payload.factors[0]["contribution_pct"] == 50.0
