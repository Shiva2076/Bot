"""Portfolio, trades, news, backtest, sectors routers."""
from fastapi import Depends, APIRouter, HTTPException
from routers.trading import get_order_service
from schemas.order_entry import EntryOrigin
from schemas.personal_trade import PersonalTradeView
from schemas.trading import PortfolioOpenRequest
from services.auth.api_key_auth import require_api_key
from services.personal.errors import TradeValidationError
from services.trading.errors import MarketDataUnavailableError, UnknownInstrumentError
from services.trading.order_service import OrderService
from services.trading.providers import portfolio_order_mapper
from services.paper_trading import paper_trading
from services.market_data import market_data_service
from services.news_aggregator import get_news_with_sentiment
from services.economic_calendar import get_upcoming_events
from engines.backtester import run_backtest
from engines.sector_rotation import get_sector_performance, get_sector_recommendation
from pydantic import BaseModel
from typing import Optional

# ── Portfolio ──────────────────────────────────────────────────────────────────
router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/summary")
async def get_portfolio_summary():
    portfolio = await paper_trading.get_portfolio()
    positions = await paper_trading.get_positions()
    stats = await paper_trading.get_stats()
    return {"portfolio": portfolio, "positions": positions, "stats": stats}


@router.get("/positions")
async def get_positions():
    return {"positions": await paper_trading.get_positions()}


@router.post("/open/{symbol}", response_model=PersonalTradeView)
async def open_position(
    symbol: str,
    request: PortfolioOpenRequest,
    service: OrderService = Depends(get_order_service),
):
    try:
        return await service.place(portfolio_order_mapper.to_market_order(symbol, request), EntryOrigin.API)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TradeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/close/{symbol}")
async def close_position(symbol: str):
    quote = await market_data_service.fetch_live_quote(symbol)
    if not quote:
        return {"error": "Could not fetch price"}
    return await paper_trading.close_position(symbol, quote["price"])
