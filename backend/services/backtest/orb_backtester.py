from datetime import datetime
from typing import Dict, List, Optional, Sequence

import pytz

from schemas.orb import OrbDecision
from schemas.personal_trade import TradeAction
from schemas.trading import Candle
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.strategies.orb.orb_signal_engine import OrbSignalEngine

IST = pytz.timezone("Asia/Kolkata")


class OrbIntradayBacktester:
    """
    Chronological ORB replay.
    Signal on bar close i using only bars[:i+1]; fill at open of bar i+1.
    """

    def __init__(self, engine: OrbSignalEngine, costs: PaperCostCalculator):
        self._engine = engine
        self._costs = costs

    def run(self, symbol: str, candles: Sequence[Candle], initial_capital: float) -> Dict:
        bars = list(candles)
        cash = initial_capital
        equity = [cash]
        trades: List[Dict] = []
        position: Optional[dict] = None
        sessions_done = set()

        for i in range(len(bars)):
            bar = bars[i]
            if position is not None:
                exit_event = self._exit_if_hit(position, bar)
                if exit_event is not None:
                    cash, trade = self._close(position, exit_event["price"], exit_event["reason"], cash)
                    trades.append(trade)
                    position = None

            day = datetime.fromtimestamp(bar.time, tz=pytz.utc).astimezone(IST).date()
            if position is None and i + 1 < len(bars) and day not in sessions_done:
                signal = self._engine.evaluate(symbol, bars[: i + 1], initial_capital if not trades else max(cash, 1))
                if (
                    signal.decision in {OrbDecision.LONG, OrbDecision.SHORT}
                    and signal.signal_time is not None
                    and int(signal.signal_time.timestamp()) == bar.time
                    and signal.quantity
                    and signal.action
                ):
                    fill = bars[i + 1]
                    opened = self._open(signal.action, fill.open, signal.quantity, signal.stop_loss, signal.target, day, cash)
                    if opened is not None:
                        cash, position = opened
                        sessions_done.add(day)

            equity.append(cash + self._unrealized(position, bar.close))

        if position is not None:
            cash, trade = self._close(position, bars[-1].close, "EOD", cash)
            trades.append(trade)
            equity.append(cash)

        return {"symbol": symbol, "trades": trades, "equity": equity, "initial_capital": initial_capital}

    def _open(self, action, raw_price, qty, stop, target, day, cash):
        leg = self._costs.leg_cost(raw_price, qty, action, is_entry=True)
        debit = leg.notional + leg.total_fees
        if debit > cash and action == TradeAction.BUY:
            return None
        if action == TradeAction.BUY:
            cash = round(cash - debit, 2)
        else:
            # short: reserve margin equal to notional + fees from cash for paper accounting
            if debit > cash:
                return None
            cash = round(cash - debit, 2)
        position = {
            "action": action,
            "qty": qty,
            "entry": leg.slipped_price,
            "stop": stop,
            "target": target,
            "entry_fees": leg.total_fees,
            "session": day,
        }
        return cash, position

    def _exit_if_hit(self, position: dict, bar: Candle) -> Optional[Dict]:
        action: TradeAction = position["action"]
        if action == TradeAction.BUY:
            if bar.low <= position["stop"]:
                return {"price": position["stop"], "reason": "SL_HIT"}
            if bar.high >= position["target"]:
                return {"price": position["target"], "reason": "TARGET_HIT"}
        else:
            if bar.high >= position["stop"]:
                return {"price": position["stop"], "reason": "SL_HIT"}
            if bar.low <= position["target"]:
                return {"price": position["target"], "reason": "TARGET_HIT"}
        return None

    def _close(self, position: dict, raw_exit: float, reason: str, cash: float):
        action: TradeAction = position["action"]
        leg = self._costs.leg_cost(raw_exit, position["qty"], action, is_entry=False)
        direction = 1 if action == TradeAction.BUY else -1
        pnl = round(
            (leg.slipped_price - position["entry"]) * position["qty"] * direction
            - position["entry_fees"]
            - leg.total_fees,
            2,
        )
        if action == TradeAction.BUY:
            cash = round(cash + leg.notional - leg.total_fees, 2)
        else:
            # release reserved notional adjusted by pnl path: return reserved entry notional then apply pnl
            cash = round(cash + position["entry"] * position["qty"] + position["entry_fees"] + pnl, 2)
        trade = {
            "action": action.value,
            "entry": position["entry"],
            "exit": leg.slipped_price,
            "qty": position["qty"],
            "pnl": pnl,
            "reason": reason,
            "session": str(position["session"]),
        }
        return cash, trade

    @staticmethod
    def _unrealized(position: Optional[dict], last: float) -> float:
        if position is None:
            return 0.0
        action: TradeAction = position["action"]
        direction = 1 if action == TradeAction.BUY else -1
        return (last - position["entry"]) * position["qty"] * direction
