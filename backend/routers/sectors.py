from fastapi import Depends, APIRouter
from services.auth.api_key_auth import require_api_key
from engines.sector_rotation import get_sector_performance, get_sector_recommendation

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/")
async def get_sectors():
    return {"sectors": await get_sector_performance()}


@router.get("/recommendation")
async def get_recommendation():
    return await get_sector_recommendation()
