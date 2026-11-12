from typing import Optional

from schemas.shadow_v2 import ShadowV2Config
from services.prediction.chain_factor_analyzer import PCR_WEIGHT
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.factor_contribution_annotator import FactorContributionAnnotator
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.technical_factor_analyzer import RVOL_WEIGHT, VWAP_WEIGHT
from services.prediction.v2.futures_volume_analyzer import FuturesVolumeAnalyzer
from services.prediction.v2.iv_rank_gate import IvRankGateEvaluator
from services.prediction.v2.oi_buildup_analyzer import OiBuildupAnalyzer
from services.prediction.v2.pcr_change_analyzer import PcrChangeAnalyzer
from services.prediction.v2.premarket_half_life import PremarketHalfLifeAnalyzer
from services.prediction.v2.shadow_scorer_v2 import (
    FuturesCandleSource,
    ShadowHistorySource,
    ShadowScorerV2,
)
from services.premarket.prediction_bridge import PREMARKET_WEIGHT


def build_shadow_scorer_v2(
    config: ShadowV2Config,
    builder: PredictionFactorBuilder,
    live_weight_budget: float,
    history: Optional[ShadowHistorySource] = None,
    futures_candles: Optional[FuturesCandleSource] = None,
) -> ShadowScorerV2:
    """Replaced factors keep the live nominal weights (no hand-tuning); ΔOI buildup is new."""
    return ShadowScorerV2(
        config=config,
        pcr=PcrChangeAnalyzer(
            builder,
            weight=PCR_WEIGHT,
            window_minutes=config.pcr_change_window_minutes,
            tolerance_minutes=config.pcr_change_tolerance_minutes,
            full_scale=config.pcr_change_full_scale,
        ),
        premarket=PremarketHalfLifeAnalyzer(builder, PREMARKET_WEIGHT, config.premarket_half_life_minutes),
        futures_volume=FuturesVolumeAnalyzer(
            builder,
            vwap_weight=VWAP_WEIGHT,
            rvol_weight=RVOL_WEIGHT,
            min_session_bars=config.futures_min_session_bars,
            atr_period=config.futures_atr_period,
            rvol_lookback_sessions=config.futures_rvol_lookback_sessions,
            rvol_min_prior_sessions=config.futures_rvol_min_prior_sessions,
        ),
        oi_buildup=OiBuildupAnalyzer(
            builder,
            weight=config.oi_buildup_weight,
            window_minutes=config.oi_buildup_window_minutes,
            tolerance_minutes=config.oi_buildup_tolerance_minutes,
            min_oi_change_pct=config.oi_buildup_min_oi_change_pct,
            min_price_change_pct=config.oi_buildup_min_price_change_pct,
            full_scale_pct=config.oi_buildup_full_scale_pct,
        ),
        iv_gate=IvRankGateEvaluator(
            lookback_sessions=config.iv_rank_lookback_sessions,
            min_sessions=config.iv_rank_min_sessions,
            block_at=config.iv_rank_block_buying_at,
        ),
        scorer=PredictionScorer(),
        annotator=FactorContributionAnnotator(),
        weight_budget=round(live_weight_budget + config.oi_buildup_weight, 4),
        history=history,
        futures_candles=futures_candles,
    )
