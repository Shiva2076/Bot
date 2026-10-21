from fastapi import APIRouter, Depends, HTTPException
from services.auth.api_key_auth import require_api_key
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from repositories.premarket_repository import PremarketRepository
from schemas.premarket import PremarketHistoryResponse, PremarketReport
from services.trading.errors import MarketDataUnavailableError
from services.trading.providers import premarket_analyzer_service

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/latest", response_model=PremarketReport)
async def get_latest_premarket(force: bool = False, db: AsyncSession = Depends(get_db)):
    try:
        report = await premarket_analyzer_service.analyze(force=force)
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    try:
        await PremarketRepository(db).upsert(report)
    except Exception as e:
        # Report is still useful when DB persistence is down (e.g. DNS/Supabase outage).
        print(f"Premarket persist skipped: {e}")
        await db.rollback()
    return report


@router.get("/history", response_model=PremarketHistoryResponse)
async def get_premarket_history(limit: int = 20, db: AsyncSession = Depends(get_db)):
    rows = await PremarketRepository(db).list_recent(max(1, min(limit, 100)))
    return PremarketHistoryResponse(
        reports=[PremarketReport.model_validate(row.payload) for row in rows]
    )
