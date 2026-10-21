from fastapi import Depends, APIRouter, HTTPException

from config import settings
from services.auth.api_key_auth import require_api_key
from services.backtest.orb_backtester import OrbIntradayBacktester
from services.backtest.orb_metrics import OrbMetricsReporter
from services.backtest.walk_forward import WalkForwardEvaluator
from services.backtest.yahoo_intraday_loader import YahooIntradayLoader
from services.market_data import market_data_service
from engines.backtester import run_backtest
from services.strategies.orb.orb_config import OrbStrategyConfig
from services.strategies.orb.orb_signal_engine import OrbSignalEngine
from services.trading.providers import paper_cost_calculator, position_sizer

router = APIRouter(dependencies=[Depends(require_api_key)])


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


@router.get("/orb")
async def run_orb_backtest(
    symbol: str = "RELIANCE.NS",
    period: str = "60d",
    capital: float = 1000000,
    train_ratio: float = 0.7,
    folds: int = 3,
):
    candles = YahooIntradayLoader().load(symbol, period=period, interval="5m")
    if len(candles) < 80:
        raise HTTPException(status_code=400, detail="Not enough intraday history for ORB backtest")
    engine = OrbSignalEngine(
        OrbStrategyConfig(
            range_minutes=settings.orb_range_minutes,
            reward_r=settings.orb_reward_r,
            invalid_after_hour=settings.orb_invalid_after_hour,
            invalid_after_minute=settings.orb_invalid_after_minute,
            require_vwap=settings.orb_require_vwap,
            require_volume=settings.orb_require_volume,
            volume_ma_period=settings.orb_volume_ma_period,
            volume_ma_mult=settings.orb_volume_ma_mult,
        ),
        position_sizer,
    )
    evaluator = WalkForwardEvaluator(OrbIntradayBacktester(engine, paper_cost_calculator), OrbMetricsReporter())
    return evaluator.evaluate(symbol, candles, capital, train_ratio=train_ratio, folds=folds)
