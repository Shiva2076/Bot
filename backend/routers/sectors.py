from fastapi import APIRouter
from engines.sector_rotation import get_sector_performance, get_sector_recommendation

router = APIRouter()


@router.get("/")
async def get_sectors():
    return {"sectors": await get_sector_performance()}


@router.get("/recommendation")
async def get_recommendation():
    return await get_sector_recommendation()
