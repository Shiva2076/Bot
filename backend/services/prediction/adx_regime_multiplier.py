from typing import Optional


class AdxRegimeMultiplier:
    """Non-directional ADX filter: scales trend strength without voting bullish/bearish."""

    def __init__(self, trend_adx: float, range_adx: float, range_multiplier: float, trend_multiplier: float):
        self._trend_adx = trend_adx
        self._range_adx = range_adx
        self._range_multiplier = range_multiplier
        self._trend_multiplier = trend_multiplier

    def multiplier(self, adx: Optional[float]) -> float:
        if adx is None:
            return 1.0
        if adx < self._range_adx:
            return self._range_multiplier
        if adx >= self._trend_adx:
            return self._trend_multiplier
        span = self._trend_adx - self._range_adx
        if span <= 0:
            return 1.0
        t = (adx - self._range_adx) / span
        return round(self._range_multiplier + t * (self._trend_multiplier - self._range_multiplier), 3)
