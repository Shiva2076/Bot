from datetime import date, datetime, timezone

from fastapi import Depends, APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.options import OptionChain, OptionExpiries, OptionUnderlying
from schemas.prediction import OptionPrediction
from schemas.prediction_log import PredictionLogList
from schemas.prediction_log_resolve import PredictionLogResolveResult
from services.auth.api_key_auth import require_api_key
from services.trading.errors import MarketDataUnavailableError, UnknownInstrumentError
from services.trading.providers import (
    option_chain_service,
    option_prediction_service,
    prediction_log_query_service,
    prediction_outcome_resolver,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/expiries", response_model=OptionExpiries)
async def get_expiries(underlying: OptionUnderlying):
    try:
        return await option_chain_service.get_expiries(underlying)
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/chain", response_model=OptionChain)
async def get_chain(underlying: OptionUnderlying, expiry: date):
    try:
        return await option_chain_service.get_chain(underlying, expiry)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/prediction", response_model=OptionPrediction)
async def get_prediction(
    underlying: OptionUnderlying,
    expiry: date,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await option_prediction_service.predict(
            underlying, expiry, session=db, force=force
        )
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/prediction/logs", response_model=PredictionLogList)
async def list_prediction_logs(
    limit: int = Query(default=50, ge=1, le=200),
    exclude_pre_fix: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    return await prediction_log_query_service.list_recent(db, limit, exclude_pre_fix)


@router.post("/prediction/logs/resolve", response_model=PredictionLogResolveResult)
async def resolve_prediction_outcomes(db: AsyncSession = Depends(get_db)):
    count = await prediction_outcome_resolver.resolve_due(db, datetime.now(timezone.utc))
    return PredictionLogResolveResult(resolved=count)
