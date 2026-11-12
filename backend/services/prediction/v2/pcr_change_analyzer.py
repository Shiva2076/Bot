from datetime import datetime, timedelta
from typing import List, Optional

from schemas.prediction import FactorCluster, PredictionFactor
from schemas.shadow_v2 import ChainSnapshotPoint
from services.prediction.factor_builder import PredictionFactorBuilder
from services.prediction.v2.snapshot_history import snapshot_near

PCR_CHANGE_NAME = "Δ Near-Spot PCR"


class PcrChangeAnalyzer:
    """v2 PCR: change in near-spot PCR over a window, from stored snapshots (not the PCR level).

    Rising PCR (puts gaining OI relative to calls near spot) is scored bullish, matching the
    sign convention of the v1 level factor.
    """

    def __init__(
        self,
        builder: PredictionFactorBuilder,
        weight: float,
        window_minutes: float,
        tolerance_minutes: float,
        full_scale: float,
    ):
        self._builder = builder
        self._weight = weight
        self._window = window_minutes
        self._tolerance = tolerance_minutes
        self._full_scale = full_scale

    @property
    def name(self) -> str:
        return f"{PCR_CHANGE_NAME} ({self._window:.0f}m)"

    def analyze(
        self,
        current_pcr: Optional[float],
        strike_window: float,
        now: datetime,
        history: List[ChainSnapshotPoint],
    ) -> PredictionFactor:
        if current_pcr is None:
            return self._builder.unavailable(
                name=self.name, detail="Near-spot PCR unavailable now", cluster=FactorCluster.OPTIONS
            )
        past = snapshot_near(history, now - timedelta(minutes=self._window), self._tolerance, strike_window)
        if past is None or past.near_spot_pcr is None:
            return self._builder.unavailable(
                name=self.name,
                detail=(
                    f"No stored snapshot with near-spot PCR {self._window:.0f}m ago "
                    f"(±{self._tolerance:.0f}m, window ±{strike_window:.0f})"
                ),
                cluster=FactorCluster.OPTIONS,
            )
        change = current_pcr - past.near_spot_pcr
        return self._builder.build(
            name=self.name,
            score=change / self._full_scale,
            weight=self._weight,
            detail=(
                f"Near-spot PCR {past.near_spot_pcr:.3f} → {current_pcr:.3f} ({change:+.3f}) "
                f"since {past.captured_at:%H:%M}; full scale ±{self._full_scale:.2f}"
            ),
            cluster=FactorCluster.OPTIONS,
        )
