from typing import Optional

from schemas.prediction import RegimeLabel, RegimeSnapshot
from schemas.premarket import IndiaVixSnapshot


class RawRegimeClassifier:
    """Point-in-time regime label without hysteresis; logged for later study."""

    def __init__(self, trend_adx: float, range_adx: float, volatile_vix: float):
        self._trend_adx = trend_adx
        self._range_adx = range_adx
        self._volatile_vix = volatile_vix

    def classify(
        self, adx: Optional[float], vix: Optional[IndiaVixSnapshot], atm_iv: Optional[float]
    ) -> RegimeSnapshot:
        vix_value = vix.value if vix is not None and vix.available else None
        vix_change = vix.change_pct if vix is not None and vix.available else None
        return RegimeSnapshot(
            label=self._label(adx, vix_value),
            adx=adx,
            vix=vix_value,
            vix_change_pct=vix_change,
            atm_iv=atm_iv,
        )

    def _label(self, adx: Optional[float], vix: Optional[float]) -> RegimeLabel:
        if vix is not None and vix >= self._volatile_vix:
            return RegimeLabel.VOLATILE
        if adx is None:
            return RegimeLabel.UNKNOWN
        if adx >= self._trend_adx:
            return RegimeLabel.TRENDING
        if adx < self._range_adx:
            return RegimeLabel.RANGE
        return RegimeLabel.TRANSITION
