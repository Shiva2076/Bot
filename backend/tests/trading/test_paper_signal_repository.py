import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings
from database import Base
from models.paper_signal import PaperSignalRecord
from repositories.paper_signal_repository import (
    PaperSignalRepository,
    SignalAuditPersistenceError,
    SignalNotFoundError,
)
from schemas.options import OptionType, OptionUnderlying
from schemas.paper_engine import (
    PaperExecutionStatus,
    PaperLifecycleEvent,
    PaperSignalCreate,
    PaperSignalEligibility,
    PaperSignalEventRecord,
)
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction


def _create_payload(
    underlying: OptionUnderlying = OptionUnderlying.NIFTY,
    direction: PredictionDirection = PredictionDirection.CALL,
    eligibility: PaperSignalEligibility = PaperSignalEligibility.ELIGIBLE,
    score: float = 80.0,
    trade_id: int = None,
) -> PaperSignalCreate:
    now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)
    return PaperSignalCreate(
        signal_uuid=str(uuid.uuid4()),
        session_date=date(2026, 10, 23),
        generated_at=now,
        underlying=underlying,
        strategy="OPTION_PREDICTION",
        direction=direction,
        score=score,
        scorer_version="v1.3_freshness",
        contract_symbol="NIFTY29OCT2625200CE",
        contract_strike=25200.0,
        contract_expiry=date(2026, 10, 29),
        contract_option_type=OptionType.CE,
        quote_ltp=140.0,
        quote_bid=139.5,
        quote_ask=140.0,
        quote_volume=12000.0,
        quote_exchange_timestamp=now,
        quote_provider="ANGEL",
        quote_freshness=DataFreshness.FRESH,
        gate_reason=GateReason.NONE if direction == PredictionDirection.CALL else GateReason.PREMARKET_WAIT,
        premarket_action=RecommendedAction.WATCH,
        eligibility_status=eligibility,
        execution_status=PaperExecutionStatus.PENDING if eligibility == PaperSignalEligibility.ELIGIBLE else PaperExecutionStatus.SKIPPED,
        rejection_reasons=[] if eligibility == PaperSignalEligibility.ELIGIBLE else ["Wait trigger active"],
        trade_id=trade_id,
        events=[
            PaperSignalEventRecord(
                timestamp=now,
                event_type=PaperLifecycleEvent.SIGNAL_GENERATED,
                details={"score": score},
            )
        ],
    )


@asynccontextmanager
async def _isolated_session():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unreachable: {type(exc).__name__}")
    transaction = await conn.begin()
    schema = f"test_paper_repo_{uuid.uuid4().hex[:12]}"
    try:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await conn.run_sync(Base.metadata.create_all)
        session = AsyncSession(bind=conn)
        yield session
    finally:
        await transaction.rollback()
        await conn.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_repository_add_and_get():
    async with _isolated_session() as session:
        repo = PaperSignalRepository(session)
        data = _create_payload(OptionUnderlying.NIFTY, PredictionDirection.CALL, PaperSignalEligibility.ELIGIBLE, 85.0)

        record = await repo.add(data)
        assert record.id is not None
        assert record.signal_uuid == data.signal_uuid
        assert record.underlying == "NIFTY"
        assert record.eligibility_status == "ELIGIBLE"

        fetched = await repo.get(record.id)
        assert fetched.id == record.id
        assert fetched.signal_uuid == data.signal_uuid
        assert len(fetched.events) == 1
        assert fetched.events[0]["event_type"] == "SIGNAL_GENERATED"

        by_uuid = await repo.get_by_uuid(data.signal_uuid)
        assert by_uuid is not None
        assert by_uuid.id == record.id


@pytest.mark.asyncio
async def test_repository_persists_repeated_and_rejected_signals():
    async with _isolated_session() as session:
        repo = PaperSignalRepository(session)

        # 1. Actionable signal
        sig1_data = _create_payload(OptionUnderlying.NIFTY, PredictionDirection.CALL, PaperSignalEligibility.ELIGIBLE, 85.0)
        sig1 = await repo.add(sig1_data)

        # 2. Repeated duplicate signal
        sig2_data = _create_payload(OptionUnderlying.NIFTY, PredictionDirection.CALL, PaperSignalEligibility.REJECTED_DUPLICATE, 84.0)
        sig2_data.rejection_reasons = ["Open position already exists for underlying NIFTY"]
        sig2_data.events.append(
            PaperSignalEventRecord(
                timestamp=datetime(2026, 10, 23, 10, 5, 0, tzinfo=timezone.utc),
                event_type=PaperLifecycleEvent.DUPLICATE_SUPPRESSED,
                details={"existing_signal_id": sig1.id},
            )
        )
        sig2 = await repo.add(sig2_data)

        # 3. Non-actionable WAIT signal
        sig3_data = _create_payload(OptionUnderlying.BANKNIFTY, PredictionDirection.WAIT, PaperSignalEligibility.NON_ACTIONABLE, 40.0)
        sig3 = await repo.add(sig3_data)

        # 4. Stale quote rejected signal
        sig4_data = _create_payload(OptionUnderlying.SENSEX, PredictionDirection.PUT, PaperSignalEligibility.REJECTED_GATE, 60.0)
        sig4_data.quote_freshness = DataFreshness.STALE
        sig4_data.rejection_reasons = ["Quote freshness is STALE"]
        sig4 = await repo.add(sig4_data)

        signals = await repo.list_for_session(session_date=date(2026, 10, 23))
        assert len(signals) == 4
        uuids = {s.signal_uuid for s in signals}
        assert len(uuids) == 4  # All independent UUIDs

        counts = await repo.count_eligibility_by_session(date(2026, 10, 23))
        assert counts.get("ELIGIBLE") == 1
        assert counts.get("REJECTED_DUPLICATE") == 1
        assert counts.get("NON_ACTIONABLE") == 1
        assert counts.get("REJECTED_GATE") == 1


@pytest.mark.asyncio
async def test_repository_link_trade_and_append_event():
    async with _isolated_session() as session:
        repo = PaperSignalRepository(session)
        data = _create_payload(OptionUnderlying.NIFTY, PredictionDirection.CALL, PaperSignalEligibility.ELIGIBLE, 88.0)
        sig = await repo.add(data)

        now = datetime(2026, 10, 23, 10, 0, 5, tzinfo=timezone.utc)
        event_fill = PaperSignalEventRecord(
            timestamp=now,
            event_type=PaperLifecycleEvent.PAPER_ENTRY_FILLED,
            details={"fill_price": 140.05, "quantity": 65, "trade_id": 42},
        )
        updated = await repo.link_trade(sig.id, trade_id=42, event=event_fill)
        assert updated.trade_id == 42
        assert updated.execution_status == "EXECUTED"
        assert len(updated.events) == 2
        assert updated.events[1]["event_type"] == "PAPER_ENTRY_FILLED"

        # Append exit event
        exit_now = datetime(2026, 10, 23, 11, 0, 0, tzinfo=timezone.utc)
        event_exit = PaperSignalEventRecord(
            timestamp=exit_now,
            event_type=PaperLifecycleEvent.PAPER_EXIT_TRIGGERED,
            details={"exit_price": 165.0, "reason": "TARGET_HIT"},
        )
        after_exit = await repo.append_event(sig.id, event_exit)
        assert len(after_exit.events) == 3
        assert after_exit.events[2]["event_type"] == "PAPER_EXIT_TRIGGERED"


@pytest.mark.asyncio
async def test_repository_get_unknown_signal_raises():
    mock_session = AsyncMock()
    mock_session.get.return_value = None
    repo = PaperSignalRepository(mock_session)

    with pytest.raises(SignalNotFoundError, match="ID 9999 not found"):
        await repo.get(9999)


@pytest.mark.asyncio
async def test_repository_surfaces_persistence_error():
    mock_session = MagicMock()
    mock_session.flush = AsyncMock(side_effect=RuntimeError("Database connection closed abruptly"))
    repo = PaperSignalRepository(mock_session)
    data = _create_payload(OptionUnderlying.NIFTY, PredictionDirection.CALL, PaperSignalEligibility.ELIGIBLE, 70.0)

    with pytest.raises(SignalAuditPersistenceError, match="Database connection closed abruptly"):
        await repo.add(data)


@pytest.mark.asyncio
async def test_concurrent_signal_writes():
    """Verify concurrent writes from multiple sessions succeed and assign distinct IDs."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unreachable: {type(exc).__name__}")

    schema = f"test_paper_concurrent_{uuid.uuid4().hex[:12]}"
    await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    await conn.execute(text(f'SET search_path TO "{schema}"'))
    await conn.run_sync(Base.metadata.create_all)
    await conn.commit()
    await conn.close()

    async def _insert_one(idx: int):
        conn_i = await engine.connect()
        await conn_i.execute(text(f'SET search_path TO "{schema}"'))
        session_i = AsyncSession(bind=conn_i, expire_on_commit=False)
        try:
            repo_i = PaperSignalRepository(session_i)
            data = _create_payload(
                OptionUnderlying.NIFTY, PredictionDirection.CALL, PaperSignalEligibility.ELIGIBLE, 70.0 + idx
            )
            rec = await repo_i.add(data)
            rec_id = rec.id
            await session_i.commit()
            return rec_id
        finally:
            await conn_i.close()

    try:
        results = await asyncio.gather(*(_insert_one(i) for i in range(10)))
        assert len(results) == 10
        assert len(set(results)) == 10
    finally:
        conn_cleanup = await engine.connect()
        await conn_cleanup.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await conn_cleanup.commit()
        await conn_cleanup.close()
        await engine.dispose()

