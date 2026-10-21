import pytest

from schemas.personal_trade import TradeAction
from schemas.trading import Instrument, InstrumentKind, MarketOrderRequest
from services.personal.errors import TradeValidationError
from services.trading.order_validator import OrderValidator


def test_option_sell_rejected():
    validator = OrderValidator()
    with pytest.raises(TradeValidationError):
        validator.validate_order(
            MarketOrderRequest(symbol="NIFTY27OCT2622900CE", action=TradeAction.SELL, lots=1),
            Instrument(symbol="NIFTY27OCT2622900CE", name="x", kind=InstrumentKind.OPTION, lot_size=65),
            100.0,
        )


def test_symbol_allows_40_chars():
    symbol = "BANKNIFTY23NOV2656100CE"  # 23 chars
    req = MarketOrderRequest(symbol=symbol, action=TradeAction.BUY, lots=1)
    assert req.symbol == symbol


def test_stop_must_be_below_for_buy():
    validator = OrderValidator()
    with pytest.raises(TradeValidationError):
        validator.validate_order(
            MarketOrderRequest(symbol="RELIANCE.NS", action=TradeAction.BUY, lots=1, stop_loss=110),
            Instrument(symbol="RELIANCE.NS", name="R", kind=InstrumentKind.STOCK, lot_size=1),
            100.0,
        )
