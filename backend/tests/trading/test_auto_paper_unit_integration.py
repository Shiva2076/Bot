"""SqlAutoPaperUnit against Postgres in a throwaway schema: a real AUTO_PAPER order and square-off."""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings
from database import Base
from models import paper_signal, prediction_log, trade  # noqa: F401  (register tables)
from models.paper_signal import PaperSignalRecord
from models.trade import Trade
from repositories.trade_repository import TradeRepository
from schemas.options import OptionType, OptionUnderlying
from schemas.paper_engine import PaperExecutionStatus, PaperSignalCreate, PaperSignalEligibility
from schemas.personal_trade import TradeAction
from schemas.prediction import PredictionDirection
from schemas.premarket import RecommendedAction
from schemas.trading import ExitReason, MarketOrderRequest
from services.personal.errors import TradeValidationError
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.auto_paper_unit import SqlAutoPaperUnit
from tests.trading.order_entry_fakes import (
    OPTION,
    REGULAR_SESSION,
    FakePredictions,
    FakePremarket,
    ScriptedCalendar,
    costs,
    gates,
    order_service,
)


@asynccontextmanager
async def isolated_session():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unreachable: {type(exc).__name__}")
    transaction = await conn.begin()
    schema = f"test_auto_paper_{uuid.uuid4().hex[:12]}"
    try:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await conn.run_sync(Base.metadata.create_all)
        yield AsyncSession(bind=conn, expire_on_commit=False)
    finally:
        await transaction.rollback()
        await conn.close()
        await engine.dispose()


def unit_for(session, premarket=RecommendedAction.WATCH, predicted_symbol=OPTION.symbol):
    entry_gates = gates(ScriptedCalendar(REGULAR_SESSION), FakePremarket(premarket), FakePredictions(predicted_symbol))
    return SqlAutoPaperUnit(
        session,
        lambda s: order_service(TradeRepository(s), OPTION, entry_gates, ltp=100.0),
        PersonalTradeMapper(PnlCalculator()),
        costs(),
    )


def signal(day):
    return PaperSignalCreate(
        signal_uuid=str(uuid.uuid4()), session_date=day, generated_at=datetime.now(timezone.utc),
        underlying=OptionUnderlying.NIFTY, strategy="AUTO_OPTION_PREDICTION", direction=PredictionDirection.CALL,
        score=0.4, scorer_version="test", contract_symbol=OPTION.symbol, contract_option_type=OptionType.CE,
        eligibility_status=PaperSignalEligibility.ELIGIBLE, execution_status=PaperExecutionStatus.PENDING,
    )


ORDER = MarketOrderRequest(symbol=OPTION.symbol, action=TradeAction.BUY, lots=1, stop_loss=95.0, target=120.0)


@pytest.mark.asyncio
async def test_auto_paper_order_is_a_system_signal_paper_trade_linked_to_its_signal():
    async with isolated_session() as session:
        unit = unit_for(session)
        day = REGULAR_SESSION.date()
        signal_id = await unit.add_signal(signal(day))
        view = await unit.place(ORDER, signal_id)
        await unit.update_signal(signal_id, execution_status=PaperExecutionStatus.EXECUTED, trade_id=view.id)
        await unit.commit()

        stored = await session.get(Trade, view.id)
        assert stored.trade_type == "PAPER" and stored.order_source == "SYSTEM_SIGNAL"
        assert stored.paper_signal_id == signal_id and stored.quantity == OPTION.lot_size
        assert [t.id for t in await unit.open_auto_trades()] == [view.id]
        assert await unit.entries_on(OptionUnderlying.NIFTY, day) == 1

        with pytest.raises(TradeValidationError):                   # same signal cannot fill twice
            await unit.place(ORDER, signal_id)


@pytest.mark.asyncio
async def test_auto_paper_entry_blocked_under_premarket_wait_and_on_signal_mismatch():
    async with isolated_session() as session:
        day = REGULAR_SESSION.date()
        waiting = unit_for(session, premarket=RecommendedAction.WAIT)
        with pytest.raises(TradeValidationError, match="WAIT blocks automatic paper entries"):
            await waiting.place(ORDER, await waiting.add_signal(signal(day)))
        mismatched = unit_for(session, predicted_symbol="NIFTY17NOV2699999CE")
        with pytest.raises(TradeValidationError, match="matching actionable system signal"):
            await mismatched.place(ORDER, await mismatched.add_signal(signal(day)))


@pytest.mark.asyncio
async def test_square_off_close_records_exit_and_signal_event():
    async with isolated_session() as session:
        unit = unit_for(session)
        signal_id = await unit.add_signal(signal(REGULAR_SESSION.date()))
        view = await unit.place(ORDER, signal_id)
        await unit.commit()
        open_trade = (await unit.open_auto_trades(for_update=True))[0]
        await unit.close_trade(open_trade, 110.0, datetime.now(timezone.utc), ExitReason.SQUARE_OFF)
        await unit.commit()

        closed = await session.get(Trade, view.id)
        assert closed.status == "CLOSED" and closed.exit_reason == "SQUARE_OFF" and closed.pnl is not None
        record = await session.get(PaperSignalRecord, signal_id)
        assert record.events[-1]["event_type"] == "PAPER_POSITION_CLOSED"
        assert await unit.open_auto_trades() == []
