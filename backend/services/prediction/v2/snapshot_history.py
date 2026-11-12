from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import pytz

from schemas.shadow_v2 import ChainSnapshotPoint, DailyAtmIv

IST = pytz.timezone("Asia/Kolkata")


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def snapshot_near(
    history: Iterable[ChainSnapshotPoint],
    target: datetime,
    tolerance_minutes: float,
    strike_window: Optional[float] = None,
) -> Optional[ChainSnapshotPoint]:
    """Snapshot captured closest to `target`, within ±tolerance and (optionally) the same strike window."""
    target = aware(target)
    limit = timedelta(minutes=tolerance_minutes)
    candidates = [
        p for p in history
        if abs(aware(p.captured_at) - target) <= limit
        and (strike_window is None or p.strike_window == strike_window)
    ]
    return min(candidates, key=lambda p: abs(aware(p.captured_at) - target), default=None)


def daily_atm_iv_series(points: Iterable[ChainSnapshotPoint]) -> List[DailyAtmIv]:
    """One ATM IV per IST session: the last reading of that day's nearest expiry."""
    by_day: Dict = {}
    for point in points:
        if point.atm_iv is None:
            continue
        day = aware(point.captured_at).astimezone(IST).date()
        if point.expiry < day:
            continue
        by_day.setdefault(day, []).append(point)
    series: List[DailyAtmIv] = []
    for day in sorted(by_day):
        nearest = min(p.expiry for p in by_day[day])
        last = max((p for p in by_day[day] if p.expiry == nearest), key=lambda p: aware(p.captured_at))
        series.append(DailyAtmIv(session_date=day, atm_iv=last.atm_iv, expiry=nearest, captured_at=last.captured_at))
    return series
