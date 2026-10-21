from fastapi import APIRouter, Depends
from services.auth.api_key_auth import require_api_key
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from repositories.trade_repository import TradeRepository
from schemas.personal_trade import PersonalHistoryResponse
from services.personal.history_aggregator import PersonalHistoryAggregator
from services.personal.personal_portfolio_service import PersonalPortfolioService
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.providers import market_data

router = APIRouter(dependencies=[Depends(require_api_key)])


def get_personal_service(session: AsyncSession = Depends(get_db)) -> PersonalPortfolioService:
    return PersonalPortfolioService(
        repository=TradeRepository(session),
        mapper=PersonalTradeMapper(PnlCalculator()),
        aggregator=PersonalHistoryAggregator(),
        market_data=market_data,
    )


@router.get("/history", response_model=PersonalHistoryResponse)
async def get_history(service: PersonalPortfolioService = Depends(get_personal_service)):
    return await service.get_history()
