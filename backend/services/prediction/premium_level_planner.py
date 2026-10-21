from schemas.options import OptionQuote
from schemas.prediction import PremiumLevels

APPROX_DELTA = 0.5
STOP_LOSS_ATR = 1.5
TARGET_ATR = 3.0
TICK_SIZE = 0.05


class PremiumLevelPlanner:
    def plan(self, quote: OptionQuote, underlying_atr: float) -> PremiumLevels:
        entry = quote.ask if quote.ask else quote.ltp
        return PremiumLevels(
            entry=self._round(entry),
            stop_loss=self._round(max(TICK_SIZE, entry - APPROX_DELTA * STOP_LOSS_ATR * underlying_atr)),
            target=self._round(entry + APPROX_DELTA * TARGET_ATR * underlying_atr),
        )

    @staticmethod
    def _round(value: float) -> float:
        return round(round(value / TICK_SIZE) * TICK_SIZE, 2)
