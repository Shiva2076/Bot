"""API routers — market data endpoints."""
from fastapi import APIRouter
from services.market_data import market_data_service, NIFTY50_STOCKS, INDICES

router = APIRouter()


@router.get("/watchlist")
async def get_watchlist():
    return {"stocks": NIFTY50_STOCKS, "indices": INDICES}


@router.get("/quotes")
async def get_all_quotes():
    quotes = await market_data_service.fetch_all_quotes()
    return {"quotes": quotes}


@router.get("/indices")
async def get_indices():
    indices = await market_data_service.fetch_index_quotes()
    return {"indices": indices}


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    quote = await market_data_service.fetch_live_quote(symbol)
    return quote or {"error": "Symbol not found"}


@router.get("/ohlcv/{symbol}")
async def get_ohlcv(symbol: str, period: str = "6mo", interval: str = "1d"):
    df = await market_data_service.fetch_ohlcv(symbol, period=period, interval=interval)
    if df is None:
        return {"error": "Data not available"}
    records = df.tail(300).to_dict(orient="records")
    return {"symbol": symbol, "interval": interval, "data": records}


@router.get("/breadth")
async def get_market_breadth():
    return await market_data_service.get_market_breadth()
