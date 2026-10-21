import asyncio
from datetime import datetime, timezone

from database import AsyncSessionLocal
from services.prediction.prediction_outcome_resolver import PredictionOutcomeResolver


class PredictionOutcomeMonitor:
    def __init__(self, resolver: PredictionOutcomeResolver, interval_seconds: float):
        self._resolver = resolver
        self._interval_seconds = interval_seconds

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as exc:
                print(f"Prediction outcome monitor error: {exc}")
            await asyncio.sleep(self._interval_seconds)

    async def check_once(self) -> None:
        async with AsyncSessionLocal() as session:
            await self._resolver.resolve_due(session, datetime.now(timezone.utc))
            await session.commit()
