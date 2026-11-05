from datetime import date, datetime, time
from typing import FrozenSet, Iterable, Tuple

import pytz
from pydantic import BaseModel, model_validator

IST = pytz.timezone("Asia/Kolkata")

PRE_OPEN_START = time(9, 0)
REGULAR_OPEN = time(9, 15)
REGULAR_CLOSE = time(15, 30)

SPECIAL_SESSION_PHASE = "SPECIAL_SESSION"


class SpecialSession(BaseModel):
    """Exchange-announced session (e.g. Muhurat) with its officially notified IST window."""

    day: date
    start: time
    end: time

    @model_validator(mode="after")
    def _end_after_start(self) -> "SpecialSession":
        if self.end <= self.start:
            raise ValueError(f"Special session on {self.day} must end after it starts")
        return self


class TradingCalendar:
    def __init__(self, holidays: FrozenSet[date], special_sessions: Iterable[SpecialSession] = ()):
        self._holidays = holidays
        self._special_sessions: Tuple[SpecialSession, ...] = tuple(special_sessions)

    @staticmethod
    def parse_holidays(raw: str) -> FrozenSet[date]:
        values = {date.fromisoformat(part.strip()) for part in raw.split(",") if part.strip()}
        return frozenset(values)

    @staticmethod
    def parse_special_sessions(raw: str) -> Tuple[SpecialSession, ...]:
        """Format: comma-separated `YYYY-MM-DDTHH:MM-HH:MM` in IST."""
        sessions = []
        for part in (p.strip() for p in raw.split(",")):
            if not part:
                continue
            day_text, window = part.split("T", 1)
            start_text, end_text = window.split("-", 1)
            sessions.append(SpecialSession(
                day=date.fromisoformat(day_text),
                start=time.fromisoformat(start_text),
                end=time.fromisoformat(end_text),
            ))
        return tuple(sessions)

    def now(self) -> datetime:
        return datetime.now(IST)

    def is_trading_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self._holidays

    def session_phase(self, moment: datetime) -> str:
        local = moment.astimezone(IST)
        clock = local.time()
        if any(s.day == local.date() and s.start <= clock <= s.end for s in self._special_sessions):
            return SPECIAL_SESSION_PHASE
        if not self.is_trading_day(local.date()):
            return "HOLIDAY_OR_WEEKEND"
        if clock < PRE_OPEN_START:
            return "PRE_MARKET"
        if clock < REGULAR_OPEN:
            return "PRE_OPEN"
        if clock <= REGULAR_CLOSE:
            return "REGULAR"
        return "POST_CLOSE"
