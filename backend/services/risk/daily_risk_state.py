from datetime import date

import pytz

IST = pytz.timezone("Asia/Kolkata")


class DailyRiskState:
    """In-process kill switch and day key. Reset automatically on a new IST calendar day."""

    def __init__(self):
        self._day: date = date.min
        self._kill_switch = False

    def _roll(self) -> None:
        today = datetime_today()
        if self._day != today:
            self._day = today
            self._kill_switch = False

    @property
    def kill_switch_active(self) -> bool:
        self._roll()
        return self._kill_switch

    def trip(self) -> None:
        self._roll()
        self._kill_switch = True

    def reset_for_tests(self) -> None:
        self._day = date.min
        self._kill_switch = False


def datetime_today() -> date:
    from datetime import datetime
    return datetime.now(IST).date()
