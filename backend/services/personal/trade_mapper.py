from datetime import datetime
from typing import Optional

import pytz

from models.trade import Trade
from schemas.personal_trade import (
    PaperTradeOpened,
    PersonalTradeView,
    PnlResult,
    TradeAction,
    TradeExitRequest,
    TradeStatus,
    TradeType,
)
from schemas.trading import Instrument, MarketOrderRequest
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.pnl_calculator import PnlCalculator


class PersonalTradeMapper:
    def __init__(self, calculator: PnlCalculator):
        self._calculator = calculator

    def order_to_entity(
        self,
        request: MarketOrderRequest,
        instrument: Instrument,
        ltp: float,
        costs: PaperCostCalculator,
    ) -> Trade:
        quantity = request.lots * instrument.lot_size
        entry = costs.leg_cost(ltp, quantity, request.action, is_entry=True)
        return Trade(
            symbol=instrument.symbol,
            action=request.action.value,
            trade_type=TradeType.MANUAL.value,
            entry_price=entry.slipped_price,
            quantity=quantity,
            invested_amount=round(entry.notional + entry.total_fees, 2),
            stop_loss=request.stop_loss,
            target_1=request.target,
            status=TradeStatus.OPEN.value,
            entry_time=datetime.now(pytz.utc),
            tags={"entry_fees": entry.model_dump(), "raw_ltp": ltp},
        )

    def paper_to_entity(self, opened: PaperTradeOpened) -> Trade:
        return Trade(
            symbol=opened.symbol,
            action=TradeAction.BUY.value,
            trade_type=TradeType.PAPER.value,
            entry_price=opened.entry_price,
            quantity=opened.quantity,
            invested_amount=opened.invested_amount,
            stop_loss=opened.stop_loss,
            target_1=opened.target_1,
            target_2=opened.target_2,
            confidence_at_entry=opened.confidence,
            market_regime_at_entry=opened.market_regime,
            status=TradeStatus.OPEN.value,
            entry_time=datetime.now(pytz.utc),
        )

    def apply_exit(
        self,
        trade: Trade,
        request: TradeExitRequest,
        costs: Optional[PaperCostCalculator] = None,
    ) -> None:
        action = TradeAction(trade.action)
        if costs is None:
            result = self._calculator.calculate(action, trade.entry_price, request.exit_price, trade.quantity)
            exit_price = round(request.exit_price, 2)
        else:
            exit_leg = costs.leg_cost(request.exit_price, trade.quantity, action, is_entry=False)
            exit_price = exit_leg.slipped_price
            direction = 1 if action == TradeAction.BUY else -1
            gross = (exit_price - trade.entry_price) * trade.quantity * direction
            entry_fees = 0.0
            if isinstance(trade.tags, dict) and "entry_fees" in trade.tags:
                entry_fees = float(trade.tags["entry_fees"].get("total_fees", 0.0))
            pnl = round(gross - entry_fees - exit_leg.total_fees, 2)
            result = PnlResult(pnl=pnl, pnl_pct=round(pnl / max(trade.invested_amount, 1e-9) * 100, 2))
            tags = dict(trade.tags or {})
            tags["exit_fees"] = exit_leg.model_dump()
            trade.tags = tags
        trade.exit_price = exit_price
        trade.exit_time = request.exit_time
        trade.exit_reason = request.exit_reason
        trade.pnl = result.pnl
        trade.pnl_pct = result.pnl_pct
        trade.status = TradeStatus.CLOSED.value
        trade.holding_days = (request.exit_time - trade.entry_time).days

    def to_view(self, trade: Trade, live_price: Optional[float]) -> PersonalTradeView:
        status = TradeStatus(trade.status)
        result = self._resolve_pnl(trade, status, live_price)
        return PersonalTradeView(
            id=trade.id,
            symbol=trade.symbol,
            action=TradeAction(trade.action),
            trade_type=TradeType(trade.trade_type),
            status=status,
            quantity=trade.quantity,
            entry_price=trade.entry_price,
            entry_time=trade.entry_time,
            invested_amount=trade.invested_amount,
            exit_price=trade.exit_price,
            exit_time=trade.exit_time,
            exit_reason=trade.exit_reason,
            current_price=live_price if status == TradeStatus.OPEN else trade.exit_price,
            stop_loss=trade.stop_loss,
            target_1=trade.target_1,
            pnl=result.pnl,
            pnl_pct=result.pnl_pct,
        )

    def _resolve_pnl(self, trade: Trade, status: TradeStatus, live_price: Optional[float]) -> PnlResult:
        if status == TradeStatus.CLOSED:
            return PnlResult(pnl=trade.pnl, pnl_pct=trade.pnl_pct)
        if live_price is None:
            return PnlResult(pnl=0.0, pnl_pct=0.0)
        return self._calculator.calculate(TradeAction(trade.action), trade.entry_price, live_price, trade.quantity)
