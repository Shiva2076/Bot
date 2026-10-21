from datetime import datetime, timezone

from schemas.premarket import RecommendedAction
from schemas.risk import PreTradeOrderContext, RiskGateDecision
from services.costs.paper_cost_calculator import PaperCostCalculator


class PreTradeRiskGate:
    """Fail-closed gate: any failed check rejects the order with explicit reasons."""

    def __init__(
        self,
        max_data_age_seconds: float,
        max_risk_per_trade_pct: float,
        daily_loss_limit_pct: float,
        max_open_positions: int,
        cost_calculator: PaperCostCalculator,
    ):
        self._max_data_age_seconds = max_data_age_seconds
        self._max_risk_per_trade_pct = max_risk_per_trade_pct
        self._daily_loss_limit_pct = daily_loss_limit_pct
        self._max_open_positions = max_open_positions
        self._costs = cost_calculator

    def evaluate(self, context: PreTradeOrderContext) -> RiskGateDecision:
        reasons = []
        reasons.extend(self._data_checks(context))
        reasons.extend(self._premarket_checks(context))
        reasons.extend(self._portfolio_checks(context))
        reasons.extend(self._trade_risk_checks(context))
        return RiskGateDecision(allowed=len(reasons) == 0, reasons=reasons)

    def _data_checks(self, context: PreTradeOrderContext) -> list:
        reasons = []
        ts = context.tick_timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
        if age > self._max_data_age_seconds:
            reasons.append(f"Critical market data stale ({age:.0f}s > {self._max_data_age_seconds:.0f}s)")
        if context.entry_price <= 0:
            reasons.append("Entry price missing or invalid")
        if context.quantity <= 0:
            reasons.append("Quantity missing or invalid")
        for warning in context.data_warnings:
            if "unavailable" in warning.lower() or "missing" in warning.lower():
                reasons.append(f"Required data issue: {warning}")
        return reasons

    def _premarket_checks(self, context: PreTradeOrderContext) -> list:
        if context.premarket_action == RecommendedAction.NO_TRADE:
            return ["Pre-market analyzer requires NO_TRADE"]
        return []

    def _portfolio_checks(self, context: PreTradeOrderContext) -> list:
        reasons = []
        if context.kill_switch_active:
            reasons.append("Daily kill switch is active")
        loss_limit = context.starting_capital * (self._daily_loss_limit_pct / 100.0)
        if context.realized_pnl_today <= -loss_limit:
            reasons.append(
                f"Daily loss limit breached ({context.realized_pnl_today:.2f} <= -{loss_limit:.2f})"
            )
        if context.open_positions >= self._max_open_positions:
            reasons.append(f"Maximum open positions reached ({self._max_open_positions})")
        return reasons

    def _trade_risk_checks(self, context: PreTradeOrderContext) -> list:
        reasons = []
        entry = self._costs.leg_cost(context.entry_price, context.quantity, context.action, is_entry=True)
        cash_needed = entry.notional + entry.total_fees
        if cash_needed > context.available_cash:
            reasons.append(f"Insufficient cash after costs (need {cash_needed:.2f}, have {context.available_cash:.2f})")
        if context.stop_loss is not None:
            stop_distance = abs(context.entry_price - context.stop_loss)
            risk_amount = stop_distance * context.quantity
            max_risk = context.starting_capital * (self._max_risk_per_trade_pct / 100.0)
            if risk_amount > max_risk:
                reasons.append(
                    f"Per-trade risk {risk_amount:.2f} exceeds limit {max_risk:.2f} "
                    f"({self._max_risk_per_trade_pct}% of capital)"
                )
        return reasons
