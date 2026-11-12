from config import settings
from schemas.trading import MarketOrderRequest, PortfolioOpenRequest
from services.risk.position_sizer import PositionSizer


class PortfolioOrderMapper:
    """Maps a watchlist signal entry onto the gated market-order path."""

    def __init__(self, sizer: PositionSizer):
        self._sizer = sizer

    def to_market_order(self, symbol: str, request: PortfolioOpenRequest) -> MarketOrderRequest:
        return MarketOrderRequest(
            symbol=symbol,
            action=request.action,
            lots=self._sizer.quantity_from_stop(settings.starting_capital, request.entry, request.stop_loss),
            stop_loss=request.stop_loss,
            target=request.target,
            override_reason=request.override_reason,
        )
