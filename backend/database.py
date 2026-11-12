from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from config import settings
from database_connect_args import AsyncpgConnectArgsFactory

db_url = make_url(settings.database_url)
print("DB URL configured:", bool(settings.database_url))
print("DB scheme:", db_url.drivername)
print("DB host:", db_url.host)
print("DB port:", db_url.port)
print("DB name:", db_url.database)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
    connect_args=AsyncpgConnectArgsFactory(settings.database_url).build(),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connectivity() -> None:
    """Raises if the database cannot accept connections."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    await engine.dispose()


async def create_tables():
    """
    Legacy schema bootstrap used only for offline/local emergency repair.

    Production and Vercel must apply schema via Alembic (see MIGRATIONS.md).
    Do not call this from FastAPI lifespan.
    """
    from models import (  # noqa: F401
        stock,
        signal,
        trade,
        journal,
        premarket_report,
        strategy_signal,
        prediction_log,
        prediction_research_outcome,
        market_snapshot,
        paper_signal,
    )
    from models.prediction_log import PRE_FIX_DATA_VERSION

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE trades ALTER COLUMN symbol TYPE VARCHAR(40)"))
        await conn.execute(text(
            "ALTER TABLE prediction_logs "
            f"ADD COLUMN IF NOT EXISTS data_version VARCHAR(40) NOT NULL DEFAULT '{PRE_FIX_DATA_VERSION}', "
            "ADD COLUMN IF NOT EXISTS lot_size INTEGER, "
            "ADD COLUMN IF NOT EXISTS cluster_scores JSON, "
            "ADD COLUMN IF NOT EXISTS regime JSON, "
            "ADD COLUMN IF NOT EXISTS shadow_features JSON, "
            "ADD COLUMN IF NOT EXISTS net_pnl_15m FLOAT, "
            "ADD COLUMN IF NOT EXISTS net_pnl_30m FLOAT, "
            "ADD COLUMN IF NOT EXISTS net_pnl_60m FLOAT"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_prediction_logs_data_version ON prediction_logs (data_version)"
        ))
        await migrate_trade_order_audit(conn)
        await migrate_prediction_gate_logging(conn)
        await migrate_paper_engine(conn)


async def migrate_trade_order_audit(conn) -> None:
    """Idempotent: adds order audit columns and tags every pre-existing trade as LEGACY."""
    from models.trade import ORDER_SOURCE_CHECK
    from schemas.order_entry import OVERRIDE_REASON_MAX_LENGTH, OrderSource

    await conn.execute(text(
        "ALTER TABLE trades "
        "ADD COLUMN IF NOT EXISTS order_source VARCHAR(20), "
        f"ADD COLUMN IF NOT EXISTS override_reason VARCHAR({OVERRIDE_REASON_MAX_LENGTH}), "
        "ADD COLUMN IF NOT EXISTS premarket_action_at_entry VARCHAR(20), "
        "ADD COLUMN IF NOT EXISTS prediction_gate_at_entry JSON"
    ))
    await conn.execute(text(
        f"UPDATE trades SET order_source = '{OrderSource.LEGACY.value}' WHERE order_source IS NULL"
    ))
    await conn.execute(text("ALTER TABLE trades ALTER COLUMN order_source SET NOT NULL"))
    await conn.execute(text("ALTER TABLE trades DROP CONSTRAINT IF EXISTS ck_trades_order_source"))
    await conn.execute(text(f"ALTER TABLE trades ADD CONSTRAINT ck_trades_order_source CHECK ({ORDER_SOURCE_CHECK})"))


async def migrate_prediction_gate_logging(conn) -> None:
    """Idempotent: nullable gate/premarket/freshness columns on prediction_logs. Old rows stay NULL."""
    await conn.execute(text(
        "ALTER TABLE prediction_logs "
        "ADD COLUMN IF NOT EXISTS gate_reason VARCHAR(40), "
        "ADD COLUMN IF NOT EXISTS premarket_action VARCHAR(20), "
        "ADD COLUMN IF NOT EXISTS premarket_generated_at TIMESTAMPTZ, "
        "ADD COLUMN IF NOT EXISTS premarket_wait_trigger VARCHAR(40), "
        "ADD COLUMN IF NOT EXISTS freshness_diagnostics JSON"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_prediction_logs_gate_reason ON prediction_logs (gate_reason)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_prediction_logs_premarket_action ON prediction_logs (premarket_action)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_prediction_logs_premarket_wait_trigger "
        "ON prediction_logs (premarket_wait_trigger)"
    ))


async def migrate_paper_engine(conn) -> None:
    """Idempotent: adds paper_signals table and indexes if not exists, and adds paper_signal_id to trades."""
    await conn.execute(text(
        "ALTER TABLE trades ADD COLUMN IF NOT EXISTS paper_signal_id INTEGER"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_trades_paper_signal_id ON trades (paper_signal_id)"
    ))
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_paper_signal_id ON trades (paper_signal_id) WHERE paper_signal_id IS NOT NULL"
    ))
    await conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_paper_signals_signal_uuid ON paper_signals (signal_uuid)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_session_date ON paper_signals (session_date)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_underlying ON paper_signals (underlying)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_strategy ON paper_signals (strategy)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_direction ON paper_signals (direction)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_eligibility_status ON paper_signals (eligibility_status)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_execution_status ON paper_signals (execution_status)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_contract_symbol ON paper_signals (contract_symbol)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paper_signals_trade_id ON paper_signals (trade_id)"
    ))

