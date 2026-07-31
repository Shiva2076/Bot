from fastapi import APIRouter
from services.paper_trading import paper_trading

router = APIRouter()


@router.get("/history")
async def get_trade_history():
    trades = await paper_trading.get_trade_history()
    return {"trades": trades, "count": len(trades)}


@router.get("/stats")
async def get_stats():
    return await paper_trading.get_stats()
