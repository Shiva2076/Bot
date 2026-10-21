from sqlalchemy.ext.asyncio import AsyncSession

from repositories.prediction_log_repository import PredictionLogRepository
from schemas.prediction_log import PredictionLogList
from services.prediction.prediction_log_mapper import PredictionLogMapper


class PredictionLogQueryService:
    def __init__(self, mapper: PredictionLogMapper):
        self._mapper = mapper

    async def list_recent(self, session: AsyncSession, limit: int, exclude_pre_fix: bool) -> PredictionLogList:
        rows = await PredictionLogRepository(session).list_recent(limit, exclude_pre_fix)
        views = [self._mapper.to_view(row) for row in rows]
        return PredictionLogList(logs=views, count=len(views))
