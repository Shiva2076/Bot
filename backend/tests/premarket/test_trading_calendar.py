from datetime import date, datetime

import pytz

from services.premarket.trading_calendar import TradingCalendar

IST = pytz.timezone("Asia/Kolkata")


class FixedCalendar(TradingCalendar):
    def __init__(self, moment: datetime, holidays):
        super().__init__(holidays)
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def test_weekend_is_not_trading_day():
    calendar = TradingCalendar(frozenset())
    assert calendar.is_trading_day(date(2026, 10, 18)) is False


def test_configured_holiday_is_not_trading_day():
    calendar = TradingCalendar(TradingCalendar.parse_holidays("2026-01-26"))
    assert calendar.is_trading_day(date(2026, 1, 26)) is False


def test_session_phases():
    holidays = frozenset()
    pre = FixedCalendar(IST.localize(datetime(2026, 10, 21, 8, 30)), holidays)
    assert pre.session_phase(pre.now()) == "PRE_MARKET"
    open_ = FixedCalendar(IST.localize(datetime(2026, 10, 21, 9, 5)), holidays)
    assert open_.session_phase(open_.now()) == "PRE_OPEN"
    regular = FixedCalendar(IST.localize(datetime(2026, 10, 21, 10, 0)), holidays)
    assert regular.session_phase(regular.now()) == "REGULAR"
