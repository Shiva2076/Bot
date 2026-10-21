from schemas.premarket import IndiaVixSnapshot, VolatilityBand
from services.trading.errors import MarketDataUnavailableError
from services.trading.failover_market_data import FailoverMarketData

INDIA_VIX_SYMBOL = "^INDIAVIX"


class IndiaVixProvider:
    def __init__(
        self,
        market_data: FailoverMarketData,
        low_threshold: float,
        high_threshold: float,
    ):
        self._market_data = market_data
        self._low = low_threshold
        self._high = high_threshold

    async def collect(self) -> IndiaVixSnapshot:
        try:
            tick = await self._market_data.get_tick(INDIA_VIX_SYMBOL)
        except MarketDataUnavailableError:
            return IndiaVixSnapshot(
                available=False,
                warning="India VIX quote unavailable from configured providers.",
            )
        return IndiaVixSnapshot(
            available=True,
            value=tick.ltp,
            change_pct=tick.change_pct,
            band=self._band(tick.ltp),
            trend=self._trend(tick.change_pct),
            timestamp=tick.timestamp,
            source=tick.provider,
            warning="VIX classifies expected volatility only; it does not predict up or down.",
        )

    def _band(self, value: float) -> VolatilityBand:
        if value < self._low:
            return VolatilityBand.LOW
        if value > self._high:
            return VolatilityBand.HIGH
        return VolatilityBand.MODERATE

    @staticmethod
    def _trend(change_pct: float) -> str:
        if change_pct > 1.0:
            return "RISING"
        if change_pct < -1.0:
            return "FALLING"
        return "FLAT"
