from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase
from config import settings

db_url = make_url(settings.database_url)
print("DB URL configured:", bool(settings.database_url))
print("DB scheme:", db_url.drivername)
print("DB host:", db_url.host)
print("DB port:", db_url.port)
print("DB name:", db_url.database)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
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


async def create_tables():
    """Create all tables on startup."""
    from models import (  # noqa: F401
        stock, signal, trade, journal, premarket_report, strategy_signal, prediction_log, market_snapshot,
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
