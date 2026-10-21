from math import floor

from services.personal.errors import TradeValidationError


class PositionSizer:
    def __init__(self, risk_per_trade_pct: float):
        self._risk_per_trade_pct = risk_per_trade_pct

    def quantity_from_stop(
        self, capital: float, entry_price: float, stop_loss: float
    ) -> int:
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            raise TradeValidationError("Stop distance must be positive for position sizing")
        risk_amount = capital * (self._risk_per_trade_pct / 100.0)
        qty = floor(risk_amount / stop_distance)
        if qty < 1:
            raise TradeValidationError("Risk budget too small for one share/lot at this stop distance")
        return qty
