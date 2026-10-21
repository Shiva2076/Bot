from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from repositories.trade_repository import TradeRepository
from schemas.personal_trade import PersonalTradeView
from schemas.prediction import ChartStructureFeatures
from schemas.trading import CandleInterval, CandleSeries, Instrument, MarketOrderRequest, OpenPositionsResponse, Tick
from services.auth.api_key_auth import require_api_key
from services.personal.errors import TradeNotFoundError, TradeValidationError
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.errors import MarketDataUnavailableError, UnknownInstrumentError
from services.trading.order_service import OrderService
from services.trading.order_validator import OrderValidator
from services.trading.providers import (
    chart_structure_query_service,
    daily_risk_state,
    instrument_catalog,
    instrument_resolver,
    market_data,
    paper_cost_calculator,
    pre_trade_risk_gate,
    premarket_analyzer_service,
)
from config import settings

router = APIRouter(dependencies=[Depends(require_api_key)])


def get_order_service(session: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(
        repository=TradeRepository(session),
        resolver=instrument_resolver,
        market_data=market_data,
        validator=OrderValidator(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        risk_gate=pre_trade_risk_gate,
        costs=paper_cost_calculator,
        daily_risk=daily_risk_state,
        premarket=premarket_analyzer_service,
        enforce_premarket_gate=settings.risk_enforce_premarket_gate,
    )


@router.get("/instruments", response_model=List[Instrument])
async def get_instruments():
    return instrument_catalog.list_all()


@router.get("/tick", response_model=Tick)
async def get_tick(symbol: str):
    try:
        return await market_data.get_tick((await instrument_resolver.resolve(symbol)).symbol)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/candles", response_model=CandleSeries)
async def get_candles(symbol: str, interval: CandleInterval = CandleInterval.ONE_MINUTE):
    try:
        return await market_data.get_candles((await instrument_resolver.resolve(symbol)).symbol, interval)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/chart-structure", response_model=ChartStructureFeatures)
async def get_chart_structure(symbol: str):
    """Shadow chart analysis; works off-session from completed candles. Not scored."""
    try:
        resolved = (await instrument_resolver.resolve(symbol)).symbol
        return await chart_structure_query_service.analyze(resolved)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/positions", response_model=OpenPositionsResponse)
async def get_positions(service: OrderService = Depends(get_order_service)):
    try:
        return OpenPositionsResponse(positions=await service.list_open_positions())
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable for positions: {e}",
        ) from e


@router.post("/orders", response_model=PersonalTradeView)
async def place_order(request: MarketOrderRequest, service: OrderService = Depends(get_order_service)):
    try:
        return await service.place(request)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TradeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/orders/{trade_id}/exit", response_model=PersonalTradeView)
async def exit_order(trade_id: int, service: OrderService = Depends(get_order_service)):
    try:
        return await service.exit(trade_id)
    except TradeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TradeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
