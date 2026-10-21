from datetime import date
from typing import List, Optional

from schemas.prediction import ChainMetrics, FactorCluster, PredictionFactor
from services.prediction.factor_builder import PredictionFactorBuilder

PCR_WEIGHT = 0.10
MAX_PAIN_WEIGHT = 0.05
OI_WALL_WEIGHT = 0.07

PCR_FULL_SCALE = 0.3
MAX_PAIN_FULL_SCALE_PCT = 0.005
OI_DELTA_SCALE_PCT = 0.30
IV_RANK_BULLISH_THRESHOLD = 20.0
IV_RANK_BEARISH_THRESHOLD = 80.0

_OI_INTERP_SCORE = {
    "CALL_BUILDUP_PUT_UNWINDING": 1.0,
    "CALL_LONG_BUILDUP": 0.7,
    "CALL_SHORT_COVERING": 0.3,
    "STABLE": 0.0,
    "MIXED": 0.0,
    "PUT_SHORT_COVERING": -0.3,
    "PUT_LONG_BUILDUP": -0.7,
    "PUT_BUILDUP_CALL_UNWINDING": -1.0,
    "UNKNOWN": 0.0,
}


class ChainFactorAnalyzer:
    def __init__(
        self,
        builder: PredictionFactorBuilder,
        oi_wall_proximity_points: float,
        max_pain_zero_dte: int,
    ):
        self._builder = builder
        self._oi_wall_proximity_points = oi_wall_proximity_points
        self._max_pain_zero_dte = max_pain_zero_dte

    def analyze(self, metrics: ChainMetrics, spot: float, expiry: date, today: date) -> List[PredictionFactor]:
        factors = [
            self._pcr(metrics),
            self._max_pain(metrics, spot, expiry, today),
            self._oi_walls(metrics, spot),
            self._oi_delta(metrics),
        ]
        iv_factor = self._iv_rank(metrics)
        if iv_factor is not None:
            factors.append(iv_factor)
        return factors

    def _pcr(self, metrics: ChainMetrics) -> PredictionFactor:
        if metrics.near_spot_pcr is None:
            return self._builder.unavailable(
                name="Put-Call Ratio",
                detail="Near-spot PCR unavailable (no OI inside the strike window)",
                cluster=FactorCluster.OPTIONS,
            )
        window = metrics.strike_window if metrics.strike_window is not None else 0.0
        return self._builder.build(
            name="Put-Call Ratio",
            score=(metrics.near_spot_pcr - 1.0) / PCR_FULL_SCALE,
            weight=PCR_WEIGHT,
            detail=(
                f"Near-spot PCR {metrics.near_spot_pcr:.2f} within ±{window:.0f} of spot "
                f"(total-chain PCR {metrics.put_call_ratio:.2f} logged only). "
                f"PCR change deferred until comparable snapshots exist"
            ),
            cluster=FactorCluster.OPTIONS,
        )

    def _max_pain(self, metrics: ChainMetrics, spot: float, expiry: date, today: date) -> PredictionFactor:
        dte = max(0, (expiry - today).days)
        weight_scale = self._max_pain_weight_scale(dte)
        effective_weight = MAX_PAIN_WEIGHT * weight_scale
        score = (metrics.max_pain - spot) / (spot * MAX_PAIN_FULL_SCALE_PCT)
        detail = (
            f"Max Pain {metrics.max_pain:.0f} vs spot {spot:.2f}; DTE={dte}; "
            f"weight scale {weight_scale:.2f} (configurable; not validated as optimal)"
        )
        if effective_weight <= 0:
            return self._builder.disabled(
                name="Max Pain",
                score=score,
                detail=detail,
                cluster=FactorCluster.OPTIONS,
            )
        return self._builder.build(
            name="Max Pain",
            score=score,
            weight=effective_weight,
            detail=detail,
            cluster=FactorCluster.OPTIONS,
        )

    def _max_pain_weight_scale(self, dte: int) -> float:
        if self._max_pain_zero_dte <= 0:
            return 1.0
        if dte >= self._max_pain_zero_dte:
            return 0.0
        return 1.0 - (dte / self._max_pain_zero_dte)

    def _oi_walls(self, metrics: ChainMetrics, spot: float) -> PredictionFactor:
        dist_put = abs(spot - metrics.put_wall)
        dist_call = abs(spot - metrics.call_wall)
        nearest = min(dist_put, dist_call)
        width = metrics.call_wall - metrics.put_wall
        score = 1.0 - 2.0 * (spot - metrics.put_wall) / width if width > 0 else 0.0
        detail = (
            f"Support {metrics.put_wall:.0f} / resistance {metrics.call_wall:.0f}; "
            f"nearest wall {nearest:.0f} pts away (need ≤{self._oi_wall_proximity_points:.0f})"
        )
        if nearest > self._oi_wall_proximity_points:
            return self._builder.disabled(
                name="OI Support / Resistance",
                score=score,
                detail=detail,
                cluster=FactorCluster.OPTIONS,
            )
        return self._builder.build(
            name="OI Support / Resistance",
            score=score,
            weight=OI_WALL_WEIGHT,
            detail=detail,
            cluster=FactorCluster.OPTIONS,
        )

    def _oi_delta(self, metrics: ChainMetrics) -> PredictionFactor:
        interp_score = _OI_INTERP_SCORE.get(metrics.oi_interpretation, 0.0)
        total_oi = metrics.total_call_oi + metrics.total_put_oi
        net_delta = (
            (metrics.call_oi_change - metrics.put_oi_change) / (total_oi * OI_DELTA_SCALE_PCT)
            if total_oi > 0
            else 0.0
        )
        return self._builder.disabled(
            name="ΔOI Dynamics",
            score=0.6 * interp_score + 0.4 * net_delta,
            detail=(
                f"OI Δ: calls {metrics.call_oi_change:+,.0f} / puts {metrics.put_oi_change:+,.0f} "
                f"→ {metrics.oi_interpretation}; in-memory totals between calls, ignores price direction"
            ),
            cluster=FactorCluster.OPTIONS,
        )

    def _iv_rank(self, metrics: ChainMetrics) -> Optional[PredictionFactor]:
        if metrics.iv_rank is None:
            return None
        rank = metrics.iv_rank
        if rank < IV_RANK_BULLISH_THRESHOLD:
            score = (IV_RANK_BULLISH_THRESHOLD - rank) / IV_RANK_BULLISH_THRESHOLD * 0.5
            label = f"Low ({rank:.0f}) — options cheap, buyers favoured"
        elif rank > IV_RANK_BEARISH_THRESHOLD:
            score = -(rank - IV_RANK_BEARISH_THRESHOLD) / (100 - IV_RANK_BEARISH_THRESHOLD) * 0.5
            label = f"High ({rank:.0f}) — options expensive, IV-crush risk for buyers"
        else:
            score = 0.0
            label = f"Moderate ({rank:.0f}) — neutral pricing environment"
        atm_str = f", ATM IV {metrics.atm_iv:.1f}%" if metrics.atm_iv else ""
        return self._builder.disabled(
            name="IV Rank",
            score=score,
            detail=f"IV Rank {label}{atm_str}; rank uses only the last 20 in-memory readings",
            cluster=FactorCluster.REGIME,
        )
