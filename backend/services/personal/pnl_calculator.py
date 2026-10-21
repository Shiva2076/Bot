from schemas.personal_trade import PnlResult, TradeAction


class PnlCalculator:
    def calculate(self, action: TradeAction, entry_price: float, exit_price: float, quantity: int) -> PnlResult:
        direction = 1 if action == TradeAction.BUY else -1
        pnl = (exit_price - entry_price) * quantity * direction
        pnl_pct = (exit_price - entry_price) / entry_price * 100 * direction
        return PnlResult(pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2))
