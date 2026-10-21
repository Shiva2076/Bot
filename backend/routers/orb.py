from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from repositories.strategy_signal_repository import StrategySignalRepository
from repositories.trade_repository import TradeRepository
from schemas.orb import OrbEvaluateRequest, OrbExecuteResponse, OrbSignal
from schemas.trading import CandleInterval
from services.auth.api_key_auth import require_api_key
from services.personal.errors import TradeValidationError
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.strategies.orb.orb_config import OrbStrategyConfig
from services.strategies.orb.orb_paper_service import OrbPaperService
from services.strategies.orb.orb_signal_engine import OrbSignalEngine
from services.trading.errors import MarketDataUnavailableError, UnknownInstrumentError
from services.trading.order_service import OrderService
from services.trading.order_validator import OrderValidator
from services.trading.providers import (
    daily_risk_state,
    instrument_resolver,
    market_data,
    paper_cost_calculator,
    position_sizer,
    pre_trade_risk_gate,
    premarket_analyzer_service,
)
router = APIRouter(dependencies=[Depends(require_api_key)])


def _orb_service(session: AsyncSession) -> OrbPaperService:
    order_service = OrderService(
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
    return OrbPaperService(
        engine=engine,
        market_data=market_data,
        resolver=instrument_resolver,
        order_service=order_service,
        signals=StrategySignalRepository(session),
        trades=TradeRepository(session),
        interval=CandleInterval(settings.orb_candle_interval),
    )


@router.post("/evaluate", response_model=OrbSignal)
async def evaluate_orb(request: OrbEvaluateRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await _orb_service(db).evaluate(request)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/execute", response_model=OrbExecuteResponse)
async def execute_orb(request: OrbEvaluateRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await _orb_service(db).execute(request)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TradeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
