from datetime import date, datetime, timezone
from typing import List

import pytz

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from repositories.paper_signal_repository import PaperSignalRepository
from repositories.trade_repository import TradeRepository
from schemas.options import OptionUnderlying
from schemas.paper_engine import AutoPaperSignalSummary, AutoPaperStatus
from schemas.order_entry import EntryOrigin
from schemas.personal_trade import PersonalTradeView
from schemas.prediction import ChartStructureFeatures
from schemas.trade_decision import TradeDecisionResponse
from schemas.trading import CandleInterval, CandleSeries, Instrument, MarketOrderRequest, OpenPositionsResponse, Tick
from services.auth.api_key_auth import require_api_key
from services.personal.errors import TradeNotFoundError, TradeValidationError
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.errors import MarketDataUnavailableError, UnknownInstrumentError
from services.trading.order_service import OrderService
from services.trading.order_validator import OrderValidator
from services.trading.providers import (
    auto_paper_engine,
    trading_calendar,
    chart_structure_query_service,
    daily_risk_state,
    instrument_catalog,
    instrument_resolver,
    market_data,
    order_entry_gates,
    paper_cost_calculator,
    pre_trade_risk_gate,
    trade_decision_service,
)

router = APIRouter(dependencies=[Depends(require_api_key)])
IST = pytz.timezone("Asia/Kolkata")


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
        gates=order_entry_gates,
    )


@router.get("/instruments", response_model=List[Instrument])
async def get_instruments():
    return instrument_catalog.list_all()


@router.get("/decision", response_model=TradeDecisionResponse)
async def get_trade_decision(
    underlying: OptionUnderlying,
    expiry: date,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """
    Unified TRADE / NO_TRADE header. Not an order authorization token;
    OrderService.place revalidates every gate on submit.
    """
    try:
        return await trade_decision_service.evaluate(underlying, expiry, db, force=force)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


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
        return await service.place(request, EntryOrigin.API)
    except UnknownInstrumentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TradeValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MarketDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/auto-paper", response_model=AutoPaperStatus)
async def get_auto_paper_status(session: AsyncSession = Depends(get_db)):
    """Automatic paper-trading engine state and today's recorded auto signals (read-only)."""
    now = datetime.now(timezone.utc)
    today = now.astimezone(IST).date()
    signals = await PaperSignalRepository(session).list_for_session(session_date=today, limit=200)
    auto = [s for s in signals if s.strategy == "AUTO_OPTION_PREDICTION"]
    open_trades = [t for t in await TradeRepository(session).list_open() if t.paper_signal_id is not None]
    return AutoPaperStatus(
        enabled=auto_paper_engine.config.enabled,
        config=auto_paper_engine.config,
        session_phase=trading_calendar.session_phase(now),
        last_run_at=auto_paper_engine.last_run_at,
        last_note=auto_paper_engine.last_note,
        open_auto_positions=len(open_trades),
        entries_today=sum(1 for s in auto if s.execution_status == "EXECUTED"),
        signals_today=[
            AutoPaperSignalSummary(
                id=s.id, generated_at=s.generated_at, underlying=s.underlying, direction=s.direction,
                contract_symbol=s.contract_symbol, entry_premium=s.entry_premium, stop_loss=s.stop_loss,
                target=s.target, eligibility_status=s.eligibility_status, execution_status=s.execution_status,
                rejection_reasons=list(s.rejection_reasons or []), trade_id=s.trade_id,
            )
            for s in auto
        ],
    )


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
