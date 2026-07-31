from fastapi import APIRouter
from services.market_data import market_data_service
from engines.backtester import run_backtest

router = APIRouter()


@router.get("/run")
async def run_backtest_endpoint(
    symbol: str = "TCS.NS",
    period: str = "5y",
    strategy: str = "rsi_macd",
    capital: float = 1000000,
):
    df = await market_data_service.fetch_ohlcv(symbol, period=period, interval="1d")
    if df is None:
        return {"error": "Could not fetch historical data"}
    result = run_backtest(df, strategy=strategy, initial_capital=capital)
    return {"symbol": symbol, "strategy": strategy, "period": period, **result}
