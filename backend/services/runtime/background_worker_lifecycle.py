import asyncio
from typing import List

from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.premarket.scheduler import PremarketScheduler
from services.prediction.prediction_outcome_monitor import PredictionOutcomeMonitor
from services.snapshots.market_snapshot_monitor import MarketSnapshotMonitor
from services.trading.risk_monitor import RiskMonitor


class BackgroundWorkerLifecycle:
    """Starts and stops persistent background monitors and schedulers."""

    def __init__(
        self,
        angel_master: AngelInstrumentMaster,
        risk_monitor: RiskMonitor,
        prediction_outcome_monitor: PredictionOutcomeMonitor,
        market_snapshot_monitor: MarketSnapshotMonitor,
        premarket_scheduler: PremarketScheduler,
    ):
        self._angel_master = angel_master
        self._risk_monitor = risk_monitor
        self._prediction_outcome_monitor = prediction_outcome_monitor
        self._market_snapshot_monitor = market_snapshot_monitor
        self._premarket_scheduler = premarket_scheduler
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        try:
            self._angel_master.start_warm()
            self._tasks = [
                asyncio.create_task(self._risk_monitor.run()),
                asyncio.create_task(self._prediction_outcome_monitor.run()),
                asyncio.create_task(self._market_snapshot_monitor.run()),
            ]
            self._premarket_scheduler.start()
            await self._premarket_scheduler.catch_up_if_needed()
        except Exception:
            await self._cleanup_started_resources()
            raise

    async def stop(self) -> None:
        await self._cleanup_started_resources()

    async def _cleanup_started_resources(self) -> None:
        try:
            self._premarket_scheduler.shutdown()
        except Exception as exc:
            print(f"Premarket scheduler shutdown error: {type(exc).__name__}")

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
