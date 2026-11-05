from datetime import datetime
from typing import Optional

import pytz

from models.trade import Trade
from schemas.order_entry import EntryAudit, OrderSource
from schemas.personal_trade import (
    PersonalTradeView,
    PnlResult,
    TradeAction,
    TradeExitRequest,
    TradeStatus,
    TradeType,
)
from schemas.trading import Instrument, MarketOrderRequest
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.errors import TradeValidationError
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
        audit: EntryAudit,
        trade_type: TradeType = TradeType.MANUAL,
        paper_signal_id: Optional[int] = None,
    ) -> Trade:
        quantity = request.lots * instrument.lot_size
        entry = costs.leg_cost(ltp, quantity, request.action, is_entry=True)
        return Trade(
            symbol=instrument.symbol,
            action=request.action.value,
            trade_type=trade_type.value if hasattr(trade_type, "value") else str(trade_type),
            entry_price=entry.slipped_price,
            quantity=quantity,
            invested_amount=round(entry.notional + entry.total_fees, 2),
            stop_loss=request.stop_loss,
            target_1=request.target,
            status=TradeStatus.OPEN.value,
            entry_time=datetime.now(pytz.utc),
            tags={"entry_fees": entry.model_dump(), "raw_ltp": ltp},
            order_source=audit.order_source.value,
            override_reason=audit.override_reason,
            premarket_action_at_entry=audit.premarket_action.value,
            prediction_gate_at_entry=audit.prediction_gate.model_dump(mode="json"),
            paper_signal_id=paper_signal_id,
        )

    def apply_exit(
        self,
        trade: Trade,
        request: TradeExitRequest,
        costs: Optional[PaperCostCalculator] = None,
    ) -> None:
        if trade.status == TradeStatus.CLOSED.value:
            raise TradeValidationError(f"Trade {trade.id} is already closed; duplicate exit prohibited")
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
        current = live_price if status == TradeStatus.OPEN else trade.exit_price
        action = TradeAction(trade.action)
        points = None
        if current is not None:
            direction = 1 if action == TradeAction.BUY else -1
            points = round((current - trade.entry_price) * direction, 2)
        return PersonalTradeView(
            id=trade.id,
            symbol=trade.symbol,
            action=action,
            trade_type=TradeType(trade.trade_type),
            status=status,
            quantity=trade.quantity,
            entry_price=trade.entry_price,
            entry_time=trade.entry_time,
            invested_amount=trade.invested_amount,
            exit_price=trade.exit_price,
            exit_time=trade.exit_time,
            exit_reason=trade.exit_reason,
            current_price=current,
            stop_loss=trade.stop_loss,
            target_1=trade.target_1,
            target_2=trade.target_2,
            pnl=result.pnl,
            pnl_pct=result.pnl_pct,
            order_source=OrderSource(trade.order_source),
            override_reason=trade.override_reason,
            holding_days=trade.holding_days,
            confidence_at_entry=trade.confidence_at_entry,
            market_regime_at_entry=trade.market_regime_at_entry,
            points_gained=points,
            tags=trade.tags if isinstance(trade.tags, dict) else None,
        )

    def _resolve_pnl(self, trade: Trade, status: TradeStatus, live_price: Optional[float]) -> PnlResult:
        if status == TradeStatus.CLOSED:
            return PnlResult(pnl=trade.pnl, pnl_pct=trade.pnl_pct)
        if live_price is None:
            return PnlResult(pnl=0.0, pnl_pct=0.0)
        return self._calculator.calculate(TradeAction(trade.action), trade.entry_price, live_price, trade.quantity)
