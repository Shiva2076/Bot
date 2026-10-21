from datetime import datetime, timedelta
from typing import List, Optional

import pytz

from schemas.prediction import SessionRange, SessionRangeKind
from schemas.trading import Candle
from services.premarket.trading_calendar import REGULAR_OPEN

IST = pytz.timezone("Asia/Kolkata")


class SessionRangeCalculator:
    """Today's Initial Balance once it has formed; the opening range before that; None before either exists."""

    def __init__(self, initial_balance_minutes: int, opening_range_minutes: int):
        self._windows = [
            (SessionRangeKind.INITIAL_BALANCE, initial_balance_minutes),
            (SessionRangeKind.OPENING_RANGE, opening_range_minutes),
        ]

    def compute(self, candles: List[Candle], interval_minutes: int, now: datetime) -> Optional[SessionRange]:
        local_now = now.astimezone(IST)
        session_open = IST.localize(datetime.combine(local_now.date(), REGULAR_OPEN))
        session_bars = [
            (datetime.fromtimestamp(c.time, IST), c)
            for c in candles
            if datetime.fromtimestamp(c.time, IST).date() == local_now.date()
        ]
        for kind, minutes in self._windows:
            window_end = session_open + timedelta(minutes=minutes)
            if local_now < window_end:
                continue
            bars = [c for start, c in session_bars if session_open <= start < window_end]
            if len(bars) < minutes // interval_minutes:
                continue
            return SessionRange(
                kind=kind,
                minutes=minutes,
                high=round(max(b.high for b in bars), 2),
                low=round(min(b.low for b in bars), 2),
            )
        return None
