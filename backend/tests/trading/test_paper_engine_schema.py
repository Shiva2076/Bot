import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from models.paper_signal import PaperSignalRecord
from models.trade import Trade
from schemas.options import OptionType, OptionUnderlying
from schemas.paper_engine import (
    PaperEngineStatus,
    PaperExecutionStatus,
    PaperLifecycleEvent,
    PaperSignalCreate,
    PaperSignalEligibility,
    PaperSignalEventRecord,
    PaperSignalView,
)
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction


def test_paper_signal_record_table_attributes():
    assert PaperSignalRecord.__tablename__ == "paper_signals"
    columns = {col.name for col in PaperSignalRecord.__table__.columns}
    required = {
        "id", "signal_uuid", "session_date", "generated_at",
        "underlying", "strategy", "direction", "score", "raw_score", "signal_score",
        "confidence", "scorer_version", "spot_level", "contract_symbol",
        "contract_strike", "contract_expiry", "contract_option_type",
        "entry_premium", "stop_loss", "target", "quote_ltp", "quote_bid", "quote_ask",
        "quote_volume", "quote_oi", "quote_exchange_timestamp", "quote_provider",
        "quote_freshness", "gate_reason", "premarket_action", "premarket_wait_trigger",
        "freshness_diagnostics", "eligibility_status", "execution_status",
        "rejection_reasons", "trade_id", "prediction_snapshot", "events", "created_at",
    }
    assert required.issubset(columns)


def test_trade_record_has_paper_signal_id():
    columns = {col.name for col in Trade.__table__.columns}
    assert "paper_signal_id" in columns


def test_paper_signal_schema_validation_and_serialization():
    now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)
    signal_uuid = str(uuid.uuid4())
    event = PaperSignalEventRecord(
        timestamp=now,
        event_type=PaperLifecycleEvent.SIGNAL_GENERATED,
        details={"score": 82.5},
    )
    schema_create = PaperSignalCreate(
        signal_uuid=signal_uuid,
        session_date=date(2026, 10, 23),
        generated_at=now,
        underlying=OptionUnderlying.NIFTY,
        strategy="OPTION_PREDICTION",
        direction=PredictionDirection.CALL,
        score=82.5,
        raw_score=75.0,
        signal_score=82.5,
        confidence=82.5,
        scorer_version="v1.3_freshness",
        spot_level=25150.0,
        contract_symbol="NIFTY29OCT2625200CE",
        contract_strike=25200.0,
        contract_expiry=date(2026, 10, 29),
        contract_option_type=OptionType.CE,
        entry_premium=145.0,
        stop_loss=120.0,
        target=195.0,
        quote_ltp=145.0,
        quote_bid=144.5,
        quote_ask=145.0,
        quote_volume=150000.0,
        quote_oi=2500000.0,
        quote_exchange_timestamp=now,
        quote_provider="ANGEL",
        quote_freshness=DataFreshness.FRESH,
        gate_reason=GateReason.NONE,
        premarket_action=RecommendedAction.WATCH,
        eligibility_status=PaperSignalEligibility.ELIGIBLE,
        execution_status=PaperExecutionStatus.PENDING,
        rejection_reasons=[],
        events=[event],
    )
    dumped = schema_create.model_dump()
    assert dumped["signal_uuid"] == signal_uuid
    assert dumped["underlying"] == "NIFTY"
    assert dumped["direction"] == "CALL"
    assert dumped["eligibility_status"] == "ELIGIBLE"
    assert len(dumped["events"]) == 1


def test_sqlite_model_persistence_and_repeated_signals():
    """Verify PaperSignalRecord model works in SQL and supports storing repeated signals independently."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        # First signal
        sig1 = PaperSignalRecord(
            signal_uuid=str(uuid.uuid4()),
            session_date=date(2026, 10, 23),
            generated_at=now,
            underlying="NIFTY",
            strategy="OPTION_PREDICTION",
            direction="CALL",
            score=70.0,
            scorer_version="v1.3_freshness",
            eligibility_status="ELIGIBLE",
            execution_status="EXECUTED",
            rejection_reasons=[],
            events=[{"timestamp": now.isoformat(), "event_type": "PAPER_ENTRY_FILLED"}],
        )
        session.add(sig1)
        session.flush()

        # Repeated signal 5 minutes later (same underlying, same session date, different uuid)
        now_later = datetime(2026, 10, 23, 10, 5, 0, tzinfo=timezone.utc)
        sig2 = PaperSignalRecord(
            signal_uuid=str(uuid.uuid4()),
            session_date=date(2026, 10, 23),
            generated_at=now_later,
            underlying="NIFTY",
            strategy="OPTION_PREDICTION",
            direction="CALL",
            score=72.0,
            scorer_version="v1.3_freshness",
            eligibility_status="REJECTED_DUPLICATE",
            execution_status="SKIPPED",
            rejection_reasons=["Open position already exists for underlying NIFTY"],
            trade_id=sig1.id,
            events=[{"timestamp": now_later.isoformat(), "event_type": "DUPLICATE_SUPPRESSED"}],
        )
        session.add(sig2)
        session.commit()

        # Verify both persisted independently
        rows = session.query(PaperSignalRecord).order_by(PaperSignalRecord.id).all()
        assert len(rows) == 2
        assert rows[0].eligibility_status == "ELIGIBLE"
        assert rows[1].eligibility_status == "REJECTED_DUPLICATE"
        assert rows[1].trade_id == rows[0].id
        assert rows[0].signal_uuid != rows[1].signal_uuid


def test_paper_engine_status_defaults():
    status = PaperEngineStatus()
    assert status.enabled is False
    assert status.mode == "PAPER_TRADING_ONLY"
    assert status.active_positions == 0
    assert status.rejection_counters == {}
    assert status.last_run_at is None


@pytest.mark.asyncio
async def test_migrate_paper_engine_idempotent_in_postgres():
    """Verify migrate_paper_engine runs idempotently against isolated postgres schema."""
    from contextlib import asynccontextmanager
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from config import settings
    from database import migrate_paper_engine

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unreachable: {type(exc).__name__}")

    transaction = await conn.begin()
    schema = f"test_paper_schema_{uuid.uuid4().hex[:12]}"
    try:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))

        # Create tables with Base.metadata
        await conn.run_sync(Base.metadata.create_all)

        # Run migrate_paper_engine first time
        await migrate_paper_engine(conn)

        # Run migrate_paper_engine second time (idempotency check)
        await migrate_paper_engine(conn)

        # Check trades has paper_signal_id
        cols_query = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'trades'"
        ))
        trade_cols = {row[0] for row in cols_query.fetchall()}
        assert "paper_signal_id" in trade_cols

        # Insert and read a signal
        now = datetime(2026, 10, 23, 11, 0, 0, tzinfo=timezone.utc)
        sig_uuid = str(uuid.uuid4())
        await conn.execute(text("""
            INSERT INTO paper_signals (
                signal_uuid, session_date, generated_at, underlying, strategy,
                direction, score, scorer_version, eligibility_status, execution_status,
                rejection_reasons, events
            ) VALUES (
                :uuid, :session_date, :generated_at, 'NIFTY', 'OPTION_PREDICTION',
                'CALL', 80.0, 'v1.3_freshness', 'ELIGIBLE', 'PENDING',
                '[]'::json, '[]'::json
            )
        """), {
            "uuid": sig_uuid,
            "session_date": date(2026, 10, 23),
            "generated_at": now,
        })

        read_res = await conn.execute(text(
            "SELECT signal_uuid, underlying, eligibility_status FROM paper_signals WHERE signal_uuid = :uuid"
        ), {"uuid": sig_uuid})
        row = read_res.fetchone()
        assert row is not None
        assert row[0] == sig_uuid
        assert row[1] == "NIFTY"
        assert row[2] == "ELIGIBLE"

    finally:
        await transaction.rollback()
        await conn.close()
        await engine.dispose()

