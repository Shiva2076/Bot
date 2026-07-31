"""API routers — AI signal generation endpoints."""
from fastapi import APIRouter, BackgroundTasks
from agents.orchestrator import generate_signal, generate_signals_batch
from services.market_data import NIFTY50_STOCKS
from services.paper_trading import paper_trading

router = APIRouter()


@router.get("/generate/{symbol}")
async def get_signal(symbol: str):
    """Generate an AI signal for a specific stock."""
    portfolio = await paper_trading.get_portfolio()
    total = portfolio.get("total_value", 1)
    invested = portfolio.get("total_invested", 0)
    heat = (invested / total * 100) if total else 0

    signal = await generate_signal(symbol, portfolio_heat=heat)
    if not signal:
        return {"error": "Could not generate signal"}
    return signal


@router.get("/batch")
async def get_batch_signals(limit: int = 5):
    """Generate signals for top N stocks from the NIFTY 50 watchlist."""
    symbols = [s["symbol"] for s in NIFTY50_STOCKS[:limit]]
    signals = await generate_signals_batch(symbols)
    return {"signals": signals, "count": len(signals)}
