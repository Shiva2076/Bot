from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List

import pytz

from schemas.personal_trade import DailyTradeSummary, PersonalTradeView, PortfolioPnlSummary, TradeStatus

IST = pytz.timezone("Asia/Kolkata")


class PersonalHistoryAggregator:
    def build_days(self, trades: List[PersonalTradeView]) -> List[DailyTradeSummary]:
        grouped: Dict[date, List[PersonalTradeView]] = defaultdict(list)
        for trade in trades:
            grouped[self._ist_date(trade.entry_time)].append(trade)
        return [self._summarize_day(day, grouped[day]) for day in sorted(grouped, reverse=True)]

    def build_summary(self, trades: List[PersonalTradeView]) -> PortfolioPnlSummary:
        open_trades = [t for t in trades if t.status == TradeStatus.OPEN]
        closed_trades = [t for t in trades if t.status == TradeStatus.CLOSED]
        wins = [t for t in closed_trades if t.pnl > 0]
        realized = sum(t.pnl for t in closed_trades)
        unrealized = sum(t.pnl for t in open_trades)
        today = datetime.now(IST).date()
        today_realized = sum(t.pnl for t in closed_trades if self._ist_date(t.exit_time) == today)
        return PortfolioPnlSummary(
            realized_pnl=round(realized, 2),
            unrealized_pnl=round(unrealized, 2),
            total_pnl=round(realized + unrealized, 2),
            today_pnl=round(today_realized + unrealized, 2),
            open_invested=round(sum(t.invested_amount for t in open_trades), 2),
            open_positions=len(open_trades),
            closed_trades=len(closed_trades),
            win_rate=round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else 0.0,
        )

    def _summarize_day(self, day: date, trades: List[PersonalTradeView]) -> DailyTradeSummary:
        closed = [t for t in trades if t.status == TradeStatus.CLOSED]
        return DailyTradeSummary(
            trade_date=day,
            entries=len(trades),
            exits=len(closed),
            wins=len([t for t in closed if t.pnl > 0]),
            losses=len([t for t in closed if t.pnl < 0]),
            realized_pnl=round(sum(t.pnl for t in closed), 2),
            unrealized_pnl=round(sum(t.pnl for t in trades if t.status == TradeStatus.OPEN), 2),
            trades=sorted(trades, key=lambda t: t.entry_time),
        )

    def _ist_date(self, moment: datetime) -> date:
        return moment.astimezone(IST).date()
