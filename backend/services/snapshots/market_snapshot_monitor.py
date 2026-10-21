import asyncio
from datetime import datetime, timezone
from typing import List

from database import AsyncSessionLocal
from schemas.options import OptionUnderlying
from services.premarket.trading_calendar import TradingCalendar
from services.snapshots.market_snapshot_recorder import MarketSnapshotRecorder

REGULAR_PHASE = "REGULAR"


class MarketSnapshotMonitor:
    def __init__(
        self,
        recorder: MarketSnapshotRecorder,
        calendar: TradingCalendar,
        underlyings: List[OptionUnderlying],
        interval_seconds: float,
    ):
        self._recorder = recorder
        self._calendar = calendar
        self._underlyings = underlyings
        self._interval_seconds = interval_seconds

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as exc:
                print(f"Market snapshot monitor error: {exc}")
            await asyncio.sleep(self._interval_seconds)

    async def check_once(self) -> None:
        now = datetime.now(timezone.utc)
        if self._calendar.session_phase(now) != REGULAR_PHASE:
            return
        for underlying in self._underlyings:
            async with AsyncSessionLocal() as session:
                await self._recorder.capture(session, underlying, now)
                await session.commit()
