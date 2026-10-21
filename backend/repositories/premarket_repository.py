from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.premarket_report import PremarketReportRecord
from schemas.premarket import PremarketReport


class PremarketRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(self, report: PremarketReport) -> PremarketReportRecord:
        existing = await self.get_by_date(report.report_date)
        payload = report.model_dump(mode="json")
        if existing:
            existing.overall_sentiment = report.overall_sentiment.value
            existing.heuristic_confidence = report.heuristic_confidence
            existing.directional_score = report.directional_score
            existing.recommended_action = report.recommended_action.value
            existing.payload = payload
            await self._session.flush()
            return existing
        row = PremarketReportRecord(
            report_date=report.report_date,
            overall_sentiment=report.overall_sentiment.value,
            heuristic_confidence=report.heuristic_confidence,
            directional_score=report.directional_score,
            recommended_action=report.recommended_action.value,
            payload=payload,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_date(self, report_date: date) -> Optional[PremarketReportRecord]:
        result = await self._session.execute(
            select(PremarketReportRecord).where(PremarketReportRecord.report_date == report_date)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int) -> List[PremarketReportRecord]:
        result = await self._session.execute(
            select(PremarketReportRecord)
            .order_by(PremarketReportRecord.report_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
