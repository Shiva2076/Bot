from datetime import datetime

import pytz

from schemas.premarket import BreadthSnapshot
from services.market_data import MarketDataService
from services.premarket.trading_calendar import TradingCalendar

IST = pytz.timezone("Asia/Kolkata")


class BreadthCollector:
    def __init__(self, market_data: MarketDataService, calendar: TradingCalendar):
        self._market_data = market_data
        self._calendar = calendar

    async def collect(self) -> BreadthSnapshot:
        phase = self._calendar.session_phase(self._calendar.now())
        raw = await self._market_data.get_market_breadth()
        total = max(int(raw.get("total", 0)), 1)
        advancing = int(raw.get("advancing", 0))
        declining = int(raw.get("declining", 0))
        unchanged = int(raw.get("unchanged", 0))
        if advancing + declining + unchanged == 0:
            return BreadthSnapshot(
                available=False,
                session_label=phase,
                warning="NIFTY 50 breadth quotes were empty.",
            )
        label = "LIVE_SESSION" if phase == "REGULAR" else "PRIOR_OR_DELAYED_SESSION"
        warning = None
        if phase in {"PRE_MARKET", "PRE_OPEN", "HOLIDAY_OR_WEEKEND", "POST_CLOSE"}:
            warning = (
                "Breadth reflects the latest available NIFTY 50 session quotes, "
                "not a guaranteed pre-open auction print."
            )
        return BreadthSnapshot(
            available=True,
            advancing=advancing,
            declining=declining,
            unchanged=unchanged,
            advance_decline_ratio=float(raw.get("advance_decline_ratio", 0.0)),
            advancing_pct=round(advancing / total * 100.0, 1),
            session_label=label,
            timestamp=datetime.now(IST),
            source="YAHOO_NIFTY50",
            warning=warning,
        )
