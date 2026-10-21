from schemas.costs import CostConfig, LegCostBreakdown, RoundTripCostEstimate
from schemas.personal_trade import TradeAction


class PaperCostCalculator:
    """
    Single place for paper trading costs. Each component is computed once per leg
    so brokerage/exchange/SEBI/GST/STT/stamp are never double-counted.
    """

    def __init__(self, config: CostConfig):
        self._config = config

    def slipped_price(self, price: float, action: TradeAction, is_entry: bool) -> float:
        bps = self._config.slippage_bps / 10_000.0
        buy_side = (action == TradeAction.BUY and is_entry) or (action == TradeAction.SELL and not is_entry)
        return round(price * (1.0 + bps if buy_side else 1.0 - bps), 4)

    def leg_cost(self, price: float, quantity: int, action: TradeAction, is_entry: bool) -> LegCostBreakdown:
        slipped = self.slipped_price(price, action, is_entry)
        notional = slipped * quantity
        brokerage = max(self._config.brokerage_flat, notional * self._config.brokerage_pct / 100.0)
        exchange = notional * self._config.exchange_txn_pct / 100.0
        sebi = notional * self._config.sebi_pct / 100.0
        stamp = notional * self._config.stamp_duty_buy_pct / 100.0 if is_entry and action == TradeAction.BUY else 0.0
        is_sell_leg = (action == TradeAction.BUY and not is_entry) or (action == TradeAction.SELL and is_entry)
        stt = notional * self._config.stt_sell_pct / 100.0 if is_sell_leg else 0.0
        taxable = brokerage + exchange
        gst = taxable * self._config.gst_pct / 100.0
        total = brokerage + exchange + sebi + stamp + stt + gst
        return LegCostBreakdown(
            notional=round(notional, 2),
            slipped_price=slipped,
            brokerage=round(brokerage, 2),
            exchange=round(exchange, 2),
            sebi=round(sebi, 2),
            stamp=round(stamp, 2),
            stt=round(stt, 2),
            gst=round(gst, 2),
            total_fees=round(total, 2),
        )

    def estimate_round_trip(
        self, entry_price: float, exit_price: float, quantity: int, action: TradeAction
    ) -> RoundTripCostEstimate:
        entry = self.leg_cost(entry_price, quantity, action, is_entry=True)
        exit_leg = self.leg_cost(exit_price, quantity, action, is_entry=False)
        slip = abs(entry.slipped_price - entry_price) * quantity + abs(exit_leg.slipped_price - exit_price) * quantity
        return RoundTripCostEstimate(
            entry=entry,
            exit=exit_leg,
            total_fees=round(entry.total_fees + exit_leg.total_fees, 2),
            total_slippage_notional=round(slip, 2),
        )

    def net_pnl(
        self, action: TradeAction, entry_price: float, exit_price: float, quantity: int
    ) -> float:
        costs = self.estimate_round_trip(entry_price, exit_price, quantity, action)
        direction = 1 if action == TradeAction.BUY else -1
        gross = (costs.exit.slipped_price - costs.entry.slipped_price) * quantity * direction
        return round(gross - costs.total_fees, 2)
