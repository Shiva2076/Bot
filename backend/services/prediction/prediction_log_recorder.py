from sqlalchemy.ext.asyncio import AsyncSession

from schemas.prediction import OptionPrediction
from repositories.prediction_log_repository import PredictionLogRepository
from services.prediction.prediction_log_mapper import PredictionLogMapper


class PredictionLogRecorder:
    def __init__(self, mapper: PredictionLogMapper):
        self._mapper = mapper

    async def record(self, session: AsyncSession, prediction: OptionPrediction) -> int:
        row = await PredictionLogRepository(session).add(self._mapper.to_create(prediction))
        return row.id
