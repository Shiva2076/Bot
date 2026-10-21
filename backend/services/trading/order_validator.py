from models.trade import Trade
from schemas.personal_trade import TradeAction, TradeStatus, TradeType
from schemas.trading import Instrument, InstrumentKind, MarketOrderRequest
from services.personal.errors import TradeValidationError


class OrderValidator:
    def validate_order(self, request: MarketOrderRequest, instrument: Instrument, ltp: float) -> None:
        is_buy = request.action == TradeAction.BUY
        if instrument.kind == InstrumentKind.OPTION and not is_buy:
            raise TradeValidationError("Options can only be bought. Exit the position to sell it back.")
        if ltp <= 0:
            raise TradeValidationError(f"No traded price available for {instrument.name}")
        if request.stop_loss is not None and (request.stop_loss >= ltp if is_buy else request.stop_loss <= ltp):
            side = "below" if is_buy else "above"
            raise TradeValidationError(f"Stop loss must be {side} the current price ₹{ltp}")
        if request.target is not None and (request.target <= ltp if is_buy else request.target >= ltp):
            side = "above" if is_buy else "below"
            raise TradeValidationError(f"Target must be {side} the current price ₹{ltp}")

    def validate_exit(self, trade: Trade) -> None:
        if trade.trade_type != TradeType.MANUAL.value:
            raise TradeValidationError("Paper trades are closed from the Portfolio page")
        if trade.status != TradeStatus.OPEN.value:
            raise TradeValidationError("Trade is already closed")
