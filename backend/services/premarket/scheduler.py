from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import AsyncSessionLocal
from repositories.premarket_repository import PremarketRepository
from services.premarket.premarket_analyzer_service import PremarketAnalyzerService
from services.premarket.trading_calendar import IST, REGULAR_OPEN, TradingCalendar


class PremarketScheduler:
    """
    Runs the pre-market analyzer on trading days.

    Downtime behavior: jobs only fire while the process is alive. On startup, if today is a
    trading day and local time is still before the regular open, a catch-up run is executed once.
    Missed runs while the Mac was asleep are not backfilled after 09:15 IST.
    """

    def __init__(
        self,
        analyzer: PremarketAnalyzerService,
        calendar: TradingCalendar,
        run_hour: int,
        run_minute: int,
    ):
        self._analyzer = analyzer
        self._calendar = calendar
        self._run_hour = run_hour
        self._run_minute = run_minute
        self._scheduler = AsyncIOScheduler(timezone=IST)

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_and_store,
            CronTrigger(
                day_of_week="mon-fri",
                hour=self._run_hour,
                minute=self._run_minute,
                timezone=IST,
            ),
            id="premarket_analyzer",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def catch_up_if_needed(self) -> None:
        now = self._calendar.now()
        if not self._calendar.is_trading_day(now.date()):
            return
        if now.time() >= REGULAR_OPEN:
            return
        await self._run_and_store()

    async def _run_and_store(self) -> None:
        now = self._calendar.now()
        if not self._calendar.is_trading_day(now.date()):
            return
        report = await self._analyzer.analyze(force=True)
        async with AsyncSessionLocal() as session:
            repo = PremarketRepository(session)
            await repo.upsert(report)
            await session.commit()
