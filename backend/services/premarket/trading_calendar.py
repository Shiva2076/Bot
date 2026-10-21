from datetime import date, datetime, time
from typing import FrozenSet

import pytz

IST = pytz.timezone("Asia/Kolkata")

PRE_OPEN_START = time(9, 0)
REGULAR_OPEN = time(9, 15)
REGULAR_CLOSE = time(15, 30)


class TradingCalendar:
    def __init__(self, holidays: FrozenSet[date]):
        self._holidays = holidays

    @staticmethod
    def parse_holidays(raw: str) -> FrozenSet[date]:
        values = {date.fromisoformat(part.strip()) for part in raw.split(",") if part.strip()}
        return frozenset(values)

    def now(self) -> datetime:
        return datetime.now(IST)

    def is_trading_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self._holidays

    def session_phase(self, moment: datetime) -> str:
        local = moment.astimezone(IST)
        if not self.is_trading_day(local.date()):
            return "HOLIDAY_OR_WEEKEND"
        clock = local.time()
        if clock < PRE_OPEN_START:
            return "PRE_MARKET"
        if clock < REGULAR_OPEN:
            return "PRE_OPEN"
        if clock <= REGULAR_CLOSE:
            return "REGULAR"
        return "POST_CLOSE"
