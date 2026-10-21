"""Portfolio, trades, news, backtest, sectors routers."""
from fastapi import Depends, APIRouter
from services.auth.api_key_auth import require_api_key
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


@router.post("/open/{symbol}")
async def open_position(symbol: str, signal: dict):
    quote = await market_data_service.fetch_live_quote(symbol)
    if not quote:
        return {"error": "Could not fetch price"}
    return await paper_trading.open_position(symbol, signal, quote["price"])


@router.post("/close/{symbol}")
async def close_position(symbol: str):
    quote = await market_data_service.fetch_live_quote(symbol)
    if not quote:
        return {"error": "Could not fetch price"}
    return await paper_trading.close_position(symbol, quote["price"])
