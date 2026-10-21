from typing import Optional

from models.trade import Trade
from schemas.personal_trade import TradeAction
from schemas.trading import ExitReason


class StopTargetEvaluator:
    def evaluate(self, trade: Trade, ltp: float) -> Optional[ExitReason]:
        is_buy = TradeAction(trade.action) == TradeAction.BUY
        if trade.stop_loss is not None and (ltp <= trade.stop_loss if is_buy else ltp >= trade.stop_loss):
            return ExitReason.SL_HIT
        if trade.target_1 is not None and (ltp >= trade.target_1 if is_buy else ltp <= trade.target_1):
            return ExitReason.TARGET_HIT
        return None
