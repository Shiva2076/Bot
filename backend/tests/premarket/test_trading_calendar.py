from datetime import date, datetime, timezone

import pytest
import pytz

from config import settings
from services.premarket.trading_calendar import SPECIAL_SESSION_PHASE, TradingCalendar

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


def _configured() -> TradingCalendar:
    return TradingCalendar(
        TradingCalendar.parse_holidays(settings.premarket_nse_holidays),
        TradingCalendar.parse_special_sessions(settings.nse_special_sessions),
    )


@pytest.mark.parametrize("day", [
    date(2026, 1, 15), date(2026, 5, 28), date(2026, 6, 26), date(2026, 9, 14),
    date(2026, 10, 20), date(2026, 11, 10), date(2026, 11, 24),
])
def test_configured_nse_2026_holidays(day):
    assert _configured().is_trading_day(day) is False


def test_nov_9_2026_is_a_trading_day():
    assert _configured().is_trading_day(date(2026, 11, 9)) is True


def test_muhurat_closed_until_special_session_configured():
    moment = IST.localize(datetime(2026, 11, 8, 18, 30))
    assert _configured().session_phase(moment) == "HOLIDAY_OR_WEEKEND"


def test_configured_special_session_window_only():
    calendar = TradingCalendar(frozenset(), TradingCalendar.parse_special_sessions("2026-11-08T18:00-19:00"))
    assert calendar.session_phase(IST.localize(datetime(2026, 11, 8, 18, 0))) == SPECIAL_SESSION_PHASE
    assert calendar.session_phase(IST.localize(datetime(2026, 11, 8, 19, 0))) == SPECIAL_SESSION_PHASE
    assert calendar.session_phase(IST.localize(datetime(2026, 11, 8, 17, 59))) == "HOLIDAY_OR_WEEKEND"
    assert calendar.session_phase(IST.localize(datetime(2026, 11, 8, 19, 1))) == "HOLIDAY_OR_WEEKEND"


def test_special_session_evaluated_in_ist_from_utc():
    calendar = TradingCalendar(frozenset(), TradingCalendar.parse_special_sessions("2026-11-08T18:00-19:00"))
    utc_moment = IST.localize(datetime(2026, 11, 8, 18, 15)).astimezone(timezone.utc)
    assert calendar.session_phase(utc_moment) == SPECIAL_SESSION_PHASE


@pytest.mark.parametrize("raw", ["2026-11-08T19:00-18:00", "2026-11-08", "2026-11-08T18:00", "bad"])
def test_malformed_special_session_rejected(raw):
    with pytest.raises(ValueError):
        TradingCalendar.parse_special_sessions(raw)


def test_weekend_and_post_close_phases():
    calendar = TradingCalendar(frozenset())
    assert calendar.session_phase(IST.localize(datetime(2026, 10, 24, 11, 0))) == "HOLIDAY_OR_WEEKEND"
    assert calendar.session_phase(IST.localize(datetime(2026, 10, 21, 15, 31))) == "POST_CLOSE"
