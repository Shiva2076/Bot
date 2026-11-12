from datetime import datetime, timedelta
from enum import Enum
from typing import List

from schemas.prediction import FactorCluster, PredictionFactor
from schemas.shadow_v2 import ChainSnapshotPoint
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.v2.snapshot_history import snapshot_near

OI_BUILDUP_NAME = "ΔOI Buildup"


class OiBuildupMode(str, Enum):
    PUT_WRITING = "PUT_WRITING"          # price up, put OI up: writers defend support (bullish)
    CALL_UNWINDING = "CALL_UNWINDING"    # price up, call OI down: call writers covering (bullish)
    CALL_WRITING = "CALL_WRITING"        # price down, call OI up: writers cap the move (bearish)
    PUT_UNWINDING = "PUT_UNWINDING"      # price down, put OI down: put writers covering (bearish)
    NONE = "NONE"


class OiBuildupAnalyzer:
    """v2 ΔOI: near-spot option OI change from stored snapshots, combined with spot direction.

    A mode counts only when the OI move is large enough AND the net writer flow
    (Δput% − Δcall%) agrees with the price direction. Otherwise the factor is neutral
    (disabled, weight 0) rather than a diluting zero vote.
    """

    def __init__(
        self,
        builder: PredictionFactorBuilder,
        weight: float,
        window_minutes: float,
        tolerance_minutes: float,
        min_oi_change_pct: float,
        min_price_change_pct: float,
        full_scale_pct: float,
    ):
        self._builder = builder
        self._weight = weight
        self._window = window_minutes
        self._tolerance = tolerance_minutes
        self._min_oi = min_oi_change_pct
        self._min_price = min_price_change_pct
        self._full_scale = full_scale_pct

    @property
    def name(self) -> str:
        return f"{OI_BUILDUP_NAME} ({self._window:.0f}m)"

    def analyze(
        self,
        spot: float,
        near_call_oi: float,
        near_put_oi: float,
        strike_window: float,
        now: datetime,
        history: List[ChainSnapshotPoint],
    ) -> PredictionFactor:
        past = snapshot_near(history, now - timedelta(minutes=self._window), self._tolerance, strike_window)
        base = (past.near_call_oi + past.near_put_oi) if past is not None else 0.0
        if past is None or base <= 0 or past.spot <= 0:
            return self._builder.unavailable(
                name=self.name,
                detail=f"No stored snapshot {self._window:.0f}m ago (±{self._tolerance:.0f}m) with near-spot OI",
                cluster=FactorCluster.OPTIONS,
            )
        d_call = (near_call_oi - past.near_call_oi) / base * 100.0
        d_put = (near_put_oi - past.near_put_oi) / base * 100.0
        price = (spot - past.spot) / past.spot * 100.0
        net = d_put - d_call
        mode = self.classify(price, d_call, d_put)
        detail = (
            f"Since {past.captured_at:%H:%M}: spot {price:+.2f}%, near call OI {d_call:+.2f}%, "
            f"near put OI {d_put:+.2f}% (of near OI); net writer flow {net:+.2f}% → {mode.value}"
        )
        if mode == OiBuildupMode.NONE:
            return self._builder.neutral(
                name=self.name, detail=f"{detail}; no buildup signal", cluster=FactorCluster.OPTIONS
            )
        return self._builder.build(
            name=self.name,
            score=net / self._full_scale,
            weight=self._weight,
            detail=detail,
            cluster=FactorCluster.OPTIONS,
        )

    def classify(self, price_pct: float, d_call_pct: float, d_put_pct: float) -> OiBuildupMode:
        if abs(price_pct) < self._min_price:
            return OiBuildupMode.NONE
        net = d_put_pct - d_call_pct
        if price_pct > 0:
            if net <= 0:
                return OiBuildupMode.NONE
            if d_put_pct >= self._min_oi:
                return OiBuildupMode.PUT_WRITING
            if d_call_pct <= -self._min_oi:
                return OiBuildupMode.CALL_UNWINDING
            return OiBuildupMode.NONE
        if net >= 0:
            return OiBuildupMode.NONE
        if d_call_pct >= self._min_oi:
            return OiBuildupMode.CALL_WRITING
        if d_put_pct <= -self._min_oi:
            return OiBuildupMode.PUT_UNWINDING
        return OiBuildupMode.NONE
