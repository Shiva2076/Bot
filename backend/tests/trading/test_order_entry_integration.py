"""
Integration: HTTP POST /api/trading/orders -> OrderService.place -> session/premarket/risk gates -> Postgres.
Runs inside a throw-away schema in a transaction that is always rolled back. Skips if Postgres is unreachable.
"""
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings
from database import migrate_trade_order_audit
from models.trade import Trade
from repositories.trade_repository import TradeRepository
from routers import trading
from schemas.order_entry import OrderSource
from schemas.premarket import RecommendedAction
from order_entry_fakes import (
    OPTION,
    REGULAR_SESSION,
    STOCK,
    WEEKEND,
    FakePredictions,
    FakePremarket,
    ScriptedCalendar,
    gates,
    order_service,
)

REASON = "Manual read of breadth divergence"
LEGACY_TRADES_DDL = (
    "CREATE TABLE trades ("
    "id SERIAL PRIMARY KEY, symbol VARCHAR(40) NOT NULL, action VARCHAR(10) NOT NULL, "
    "trade_type VARCHAR(10), entry_price FLOAT NOT NULL, quantity INTEGER NOT NULL, "
    "invested_amount FLOAT NOT NULL, status VARCHAR(10))"
)


@asynccontextmanager
async def _isolated_connection():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unreachable: {type(exc).__name__}")
    transaction = await conn.begin()
    schema = f"test_orders_{uuid.uuid4().hex[:12]}"
    try:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield conn
    finally:
        await transaction.rollback()
        await conn.close()
        await engine.dispose()


def _client(session: AsyncSession, action: RecommendedAction, *moments) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(trading.router, prefix="/api/trading")
    entry_gates = gates(
        ScriptedCalendar(*(moments or (REGULAR_SESSION,))), FakePremarket(action), FakePredictions(OPTION.symbol)
    )
    app.dependency_overrides[trading.get_order_service] = lambda: order_service(
        TradeRepository(session), STOCK, entry_gates
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": settings.app_api_key},
    )


def _body(**extra):
    return {"symbol": STOCK.symbol, "action": "BUY", "lots": 1, "stop_loss": 995.0, **extra}


async def _rows(conn):
    return (await conn.execute(text(
        "SELECT order_source, override_reason, premarket_action_at_entry FROM trades ORDER BY id"
    ))).all()


@pytest.mark.asyncio
async def test_migration_backfills_legacy_and_enforces_constraint():
    async with _isolated_connection() as conn:
        await conn.execute(text(LEGACY_TRADES_DDL))
        await conn.execute(text(
            "INSERT INTO trades (symbol, action, trade_type, entry_price, quantity, invested_amount, status) "
            "VALUES ('TCS.NS', 'BUY', 'PAPER', 100, 1, 100, 'CLOSED')"
        ))
        await migrate_trade_order_audit(conn)
        await migrate_trade_order_audit(conn)
        assert (await _rows(conn)) == [(OrderSource.LEGACY.value, None, None)]
        nullable = (await conn.execute(text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'trades' AND column_name = 'order_source'"
        ))).scalar_one()
        assert nullable == "NO"
        savepoint = await conn.begin_nested()
        with pytest.raises(IntegrityError, match="ck_trades_order_source"):
            await conn.execute(text(
                "INSERT INTO trades (symbol, action, entry_price, quantity, invested_amount, order_source) "
                "VALUES ('X', 'BUY', 1, 1, 1, 'CLIENT_SET')"
            ))
        await savepoint.rollback()


@pytest.mark.asyncio
async def test_post_order_persists_manual_override_under_wait():
    async with _isolated_connection() as conn:
        await conn.run_sync(lambda sync: Trade.__table__.create(sync))
        session = AsyncSession(bind=conn)
        async with _client(session, RecommendedAction.WAIT) as client:
            response = await client.post("/api/trading/orders", json=_body(override_reason=f"  {REASON} "))
        await session.flush()
        assert response.status_code == 200, response.text
        assert response.json()["order_source"] == OrderSource.MANUAL_OVERRIDE.value
        assert (await _rows(conn)) == [(OrderSource.MANUAL_OVERRIDE.value, REASON, RecommendedAction.WAIT.value)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action, body, moments, status, detail",
    [
        (RecommendedAction.WAIT, _body(), (), 400, "WAIT"),
        (RecommendedAction.NO_TRADE, _body(override_reason=REASON), (), 400, "NO_TRADE"),
        (RecommendedAction.WATCH, _body(override_reason=REASON), (WEEKEND,), 400, "HOLIDAY_OR_WEEKEND"),
        (RecommendedAction.WATCH, _body(order_source="SYSTEM_SIGNAL"), (), 422, "order_source"),
        (RecommendedAction.WAIT, _body(override_reason="   "), (), 422, "override_reason"),
    ],
    ids=["wait-no-reason", "no-trade-with-reason", "weekend", "client-order-source", "blank-reason"],
)
async def test_post_order_rejections_write_nothing(action, body, moments, status, detail):
    async with _isolated_connection() as conn:
        await conn.run_sync(lambda sync: Trade.__table__.create(sync))
        session = AsyncSession(bind=conn)
        async with _client(session, action, *moments) as client:
            response = await client.post("/api/trading/orders", json=body)
        await session.flush()
        assert response.status_code == status
        assert detail in response.text
        assert (await _rows(conn)) == []


@pytest.mark.asyncio
async def test_post_order_requires_api_key():
    async with _isolated_connection() as conn:
        session = AsyncSession(bind=conn)
        async with _client(session, RecommendedAction.WATCH) as client:
            response = await client.post("/api/trading/orders", json=_body(), headers={"X-API-Key": "wrong"})
        assert response.status_code == 401
