import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
import pytz
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings
from database import Base
from models.trade import Trade
from repositories.trade_repository import TradeRepository
from schemas.costs import CostConfig
from schemas.options import OptionContract, OptionType, OptionUnderlying, ParsedOptionSymbol
from schemas.order_entry import EntryOrigin, OrderSource
from schemas.personal_trade import PersonalTradeView, TradeAction, TradeExitRequest, TradeStatus, TradeType
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction
from schemas.trading import ExitReason, Instrument, InstrumentKind, MarketOrderRequest, Tick
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.options.expiry_settlement_policy import ExpirySettlementPolicy
from services.personal.errors import TradeValidationError
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.risk.daily_risk_state import DailyRiskState
from services.risk.position_sizer import PositionSizer
from services.risk.pre_trade_risk_gate import PreTradeRiskGate
from services.trading.actionable_signal_matcher import ActionableSignalMatcher, PredictionGateSnapshotMapper
from services.trading.entry_session_gate import EntrySessionGate
from services.trading.order_entry_gates import OrderEntryGates
from services.trading.order_service import OrderService
from services.trading.order_source_classifier import OrderSourceClassifier
from services.trading.order_validator import OrderValidator
from services.trading.risk_monitor import RiskMonitor
from services.trading.stop_target_evaluator import StopTargetEvaluator
from tests.trading.order_entry_fakes import (
    OPTION,
    REGULAR_SESSION,
    STOCK,
    FakeContractResolver,
    FakeMarketData,
    FakePredictions,
    FakePremarket,
    FakeRepo,
    FakeResolver,
    ScriptedCalendar,
    costs,
    gates,
    option_order,
    order_service,
    stock_order,
    tick,
)

IST = pytz.timezone("Asia/Kolkata")


def _setup_service(
    repo: FakeRepo,
    action: RecommendedAction = RecommendedAction.WATCH,
    gate_reason: GateReason = GateReason.NONE,
    ltp: float = 100.0,
    contract_symbol: str = OPTION.symbol,
) -> OrderService:
    calendar = ScriptedCalendar(REGULAR_SESSION)
    premarket = FakePremarket(action)
    predictions = FakePredictions(contract_symbol, gate_reason)
    entry_gates = gates(calendar, premarket, predictions)
    return order_service(repo, OPTION, entry_gates, ltp=ltp)


# ============================================================================
# 1. MANUAL versus PAPER Entry & Exit Validation
# ============================================================================


@pytest.mark.asyncio
async def test_manual_vs_paper_entry_creation():
    repo = FakeRepo()
    service = _setup_service(repo)

    # Manual entry from API with matching signal
    manual_view = await service.place(option_order(), EntryOrigin.API)
    assert manual_view.trade_type == TradeType.MANUAL
    assert manual_view.status == TradeStatus.OPEN
    assert repo.added[0].trade_type == "MANUAL"

    # Automatic paper entry
    paper_view = await service.place(option_order(), EntryOrigin.AUTO_PAPER, paper_signal_id=101)
    assert paper_view.trade_type == TradeType.PAPER
    assert paper_view.status == TradeStatus.OPEN
    assert repo.added[1].trade_type == "PAPER"
    assert repo.added[1].paper_signal_id == 101


def test_validator_supports_manual_and_paper_exits():
    validator = OrderValidator()
    now = datetime.now(timezone.utc)

    # Valid manual open trade
    manual_trade = Trade(
        id=1, symbol=OPTION.symbol, action="BUY", trade_type="MANUAL",
        status="OPEN", entry_price=100.0, quantity=65, invested_amount=6500.0,
        entry_time=now,
    )
    validator.validate_exit(manual_trade)  # Should not raise

    # Valid paper open trade
    paper_trade = Trade(
        id=2, symbol=OPTION.symbol, action="BUY", trade_type="PAPER",
        status="OPEN", entry_price=100.0, quantity=65, invested_amount=6500.0,
        entry_time=now,
    )
    validator.validate_exit(paper_trade)  # Should not raise

    # Closed trade rejected
    closed_trade = Trade(
        id=3, symbol=OPTION.symbol, action="BUY", trade_type="PAPER",
        status="CLOSED", entry_price=100.0, quantity=65, invested_amount=6500.0,
        entry_time=now,
    )
    with pytest.raises(TradeValidationError, match="Trade is already closed"):
        validator.validate_exit(closed_trade)

    # Unsupported trade type rejected
    other_trade = Trade(
        id=4, symbol=OPTION.symbol, action="BUY", trade_type="UNKNOWN",
        status="OPEN", entry_price=100.0, quantity=65, invested_amount=6500.0,
        entry_time=now,
    )
    with pytest.raises(TradeValidationError, match="Unsupported trade type for exit"):
        validator.validate_exit(other_trade)


@pytest.mark.asyncio
async def test_order_service_exit_closes_both_manual_and_paper():
    repo = FakeRepo()
    service = _setup_service(repo)

    await service.place(option_order(), EntryOrigin.API)
    await service.place(option_order(), EntryOrigin.AUTO_PAPER, paper_signal_id=202)

    # Exit manual trade
    exit_manual = await service.exit(1)
    assert exit_manual.status == TradeStatus.CLOSED
    assert repo.added[0].status == "CLOSED"

    # Exit paper trade
    exit_paper = await service.exit(2)
    assert exit_paper.status == TradeStatus.CLOSED
    assert repo.added[1].status == "CLOSED"

    # Exiting closed trade raises error
    with pytest.raises(TradeValidationError, match="Trade is already closed"):
        await service.exit(1)


# ============================================================================
# 2. Gate Enforcement for AUTO_PAPER
# ============================================================================


@pytest.mark.asyncio
async def test_auto_paper_cannot_carry_override_reason():
    repo = FakeRepo()
    service = _setup_service(repo)

    with pytest.raises(TradeValidationError, match="Automatic paper entries cannot carry a manual override reason"):
        await service.place(
            option_order(override_reason="Attempting to force paper entry"),
            EntryOrigin.AUTO_PAPER,
        )


@pytest.mark.asyncio
async def test_auto_paper_blocked_by_premarket_wait_and_no_trade():
    # 1. WAIT blocks AUTO_PAPER
    repo_wait = FakeRepo()
    service_wait = _setup_service(repo_wait, action=RecommendedAction.WAIT)
    with pytest.raises(TradeValidationError, match="Pre-market WAIT blocks automatic paper entries"):
        await service_wait.place(option_order(), EntryOrigin.AUTO_PAPER)

    # 2. NO_TRADE blocks AUTO_PAPER
    repo_no_trade = FakeRepo()
    service_no_trade = _setup_service(repo_no_trade, action=RecommendedAction.NO_TRADE)
    with pytest.raises(TradeValidationError, match="Pre-market NO_TRADE blocks all new entries"):
        await service_no_trade.place(option_order(), EntryOrigin.AUTO_PAPER)


@pytest.mark.asyncio
async def test_auto_paper_blocked_if_signal_not_actionable():
    # Gate reason not NONE (e.g. PREMARKET_WAIT or SPREAD_TOO_WIDE)
    repo = FakeRepo()
    service = _setup_service(repo, gate_reason=GateReason.PREMARKET_WAIT)

    with pytest.raises(TradeValidationError, match="Automatic paper entries require a matching actionable system signal"):
        await service.place(option_order(), EntryOrigin.AUTO_PAPER)


@pytest.mark.asyncio
async def test_auto_paper_blocked_if_contract_symbol_mismatched():
    repo = FakeRepo()
    service = _setup_service(repo, contract_symbol="NIFTY27OCT2625500CE")  # Different strike

    with pytest.raises(TradeValidationError, match="Automatic paper entries require a matching actionable system signal"):
        await service.place(option_order(), EntryOrigin.AUTO_PAPER)


# ============================================================================
# 3. Position Sizing and Risk Limits
# ============================================================================


def test_position_sizer_validates_stop_distance_and_budget():
    sizer = PositionSizer(risk_per_trade_pct=1.0)

    # 1% of 100,000 = 1,000 risk budget
    # Entry 100, Stop 95 -> distance 5 -> qty = 1000 / 5 = 200
    qty = sizer.quantity_from_stop(capital=100_000.0, entry_price=100.0, stop_loss=95.0)
    assert qty == 200

    # Stop distance <= 0 raises
    with pytest.raises(TradeValidationError, match="Stop distance must be positive"):
        sizer.quantity_from_stop(capital=100_000.0, entry_price=100.0, stop_loss=100.0)

    # Budget too small raises
    with pytest.raises(TradeValidationError, match="Risk budget too small"):
        sizer.quantity_from_stop(capital=1_000.0, entry_price=100.0, stop_loss=80.0)


@pytest.mark.asyncio
async def test_order_service_rejects_insufficient_cash():
    repo = FakeRepo()
    # Mock huge investment already open
    repo.open_invested_total = AsyncMock(return_value=settings.starting_capital - 100.0)
    service = _setup_service(repo)

    # Order needs more than 100 cash after costs
    with pytest.raises(TradeValidationError, match="Insufficient cash after costs"):
        await service.place(option_order(lots=5), EntryOrigin.AUTO_PAPER)


@pytest.mark.asyncio
async def test_order_service_rejects_when_max_positions_reached():
    repo = FakeRepo()
    repo.count_open = AsyncMock(return_value=settings.risk_max_open_positions)
    service = _setup_service(repo)

    with pytest.raises(TradeValidationError, match="Maximum open positions reached"):
        await service.place(option_order(), EntryOrigin.AUTO_PAPER)


# ============================================================================
# 4. Stop-Loss and Target Exits via RiskMonitor
# ============================================================================


@pytest.mark.asyncio
async def test_risk_monitor_triggers_stop_loss_and_target_for_paper_trades():
    now = datetime.now(timezone.utc)
    trade_sl = Trade(
        id=1, symbol=OPTION.symbol, action="BUY", trade_type="PAPER",
        status="OPEN", entry_price=100.0, quantity=65, stop_loss=90.0, target_1=120.0,
        invested_amount=6520.0, entry_time=now - timedelta(minutes=15),
        tags={"entry_fees": {"total_fees": 21.0}},
    )
    trade_tgt = Trade(
        id=2, symbol=OPTION.symbol, action="BUY", trade_type="PAPER",
        status="OPEN", entry_price=100.0, quantity=65, stop_loss=90.0, target_1=120.0,
        invested_amount=6520.0, entry_time=now - timedelta(minutes=10),
        tags={"entry_fees": {"total_fees": 21.0}},
    )

    # 1. Stop loss triggered at 89.0
    monitor_sl = RiskMonitor(
        market_data=FakeMarketData(tick(OPTION.symbol, ltp=89.0)),
        evaluator=StopTargetEvaluator(),
        contracts=FakeContractResolver(),
        expiry_policy=ExpirySettlementPolicy(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        costs=costs(),
        interval_seconds=60,
    )
    await monitor_sl._apply_stops([trade_sl], now)
    assert trade_sl.status == "CLOSED"
    assert trade_sl.exit_reason == "SL_HIT"
    assert trade_sl.exit_price < 89.0  # Slipped exit for SELL leg

    # 2. Target triggered at 125.0
    monitor_tgt = RiskMonitor(
        market_data=FakeMarketData(tick(OPTION.symbol, ltp=125.0)),
        evaluator=StopTargetEvaluator(),
        contracts=FakeContractResolver(),
        expiry_policy=ExpirySettlementPolicy(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        costs=costs(),
        interval_seconds=60,
    )
    await monitor_tgt._apply_stops([trade_tgt], now)
    assert trade_tgt.status == "CLOSED"
    assert trade_tgt.exit_reason == "TARGET_HIT"
    assert trade_tgt.exit_price < 125.0  # Slipped exit for SELL leg


# ============================================================================
# 5. Stale Exit Quotes and Deferred Exits
# ============================================================================


@pytest.mark.asyncio
async def test_risk_monitor_defers_exit_on_stale_or_missing_quotes():
    now = datetime.now(timezone.utc)
    trade = Trade(
        id=10, symbol=OPTION.symbol, action="BUY", trade_type="PAPER",
        status="OPEN", entry_price=100.0, quantity=65, stop_loss=90.0, target_1=120.0,
        invested_amount=6520.0, entry_time=now - timedelta(minutes=30),
    )

    # 1. Missing quote
    empty_market = AsyncMock()
    empty_market.get_ticks.return_value = {}
    monitor_missing = RiskMonitor(
        market_data=empty_market,
        evaluator=StopTargetEvaluator(),
        contracts=FakeContractResolver(),
        expiry_policy=ExpirySettlementPolicy(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        costs=costs(),
        interval_seconds=60,
    )
    await monitor_missing._apply_stops([trade], now)
    assert trade.status == "OPEN"  # Did NOT close!
    assert 10 in monitor_missing.unresolved_exposures
    assert "Quote unavailable" in monitor_missing.unresolved_exposures[10]["reason"]

    # 2. Stale quote (exchange timestamp 45s old)
    stale_ts = now - timedelta(seconds=45)
    stale_tick = Tick(
        symbol=OPTION.symbol, ltp=85.0, prev_close=100.0, change=-15.0, change_pct=-15.0,
        timestamp=now, provider="ANGEL", fetched_at=now, exchange_timestamp=stale_ts,
    )
    monitor_stale = RiskMonitor(
        market_data=FakeMarketData(stale_tick),
        evaluator=StopTargetEvaluator(),
        contracts=FakeContractResolver(),
        expiry_policy=ExpirySettlementPolicy(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        costs=costs(),
        interval_seconds=60,
        max_data_age_seconds=30.0,
    )
    await monitor_stale._apply_stops([trade], now)
    assert trade.status == "OPEN"  # Did NOT close on stale quote!
    assert 10 in monitor_stale.unresolved_exposures
    assert "Quote stale" in monitor_stale.unresolved_exposures[10]["reason"]


# ============================================================================
# 6. Expiry Settlement and Duplicate Settlement Prevention
# ============================================================================


@pytest.mark.asyncio
async def test_risk_monitor_expiry_settlement_and_idempotence():
    # 27-Oct-2026 15:35 IST (market closed, option expired)
    settle_time = IST.localize(datetime(2026, 10, 27, 15, 35)).astimezone(timezone.utc)
    trade = Trade(
        id=20, symbol="NIFTY27OCT2625000CE", action="BUY", trade_type="PAPER",
        status="OPEN", entry_price=100.0, quantity=65, stop_loss=90.0, target_1=120.0,
        invested_amount=6520.0, entry_time=settle_time - timedelta(days=2),
        tags={"entry_fees": {"total_fees": 21.0}},
    )
    option_symbol = ParsedOptionSymbol(
        underlying=OptionUnderlying.NIFTY,
        expiry=date(2026, 10, 27),
        strike=25000.0,
        option_type=OptionType.CE,
    )

    # Spot is at 25150.0 -> intrinsic for 25000 CE is 150.0
    spot_tick = Tick(
        symbol="^NSEI", ltp=25150.0, prev_close=25000.0, change=150.0, change_pct=0.6,
        timestamp=settle_time, provider="ANGEL", fetched_at=settle_time, exchange_timestamp=settle_time,
    )
    monitor = RiskMonitor(
        market_data=FakeMarketData(spot_tick),
        evaluator=StopTargetEvaluator(),
        contracts=FakeContractResolver(),
        expiry_policy=ExpirySettlementPolicy(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        costs=costs(),
        interval_seconds=60,
    )

    # First settlement run
    await monitor._settle_expired([trade], {20: option_symbol}, settle_time)
    assert trade.status == "CLOSED"
    assert trade.exit_reason == "EXPIRED"
    assert trade.exit_price == 149.925  # Slipped exit leg for 150.0
    first_pnl = trade.pnl

    # Second settlement run (retry) -> must be skipped idempotently
    await monitor._settle_expired([trade], {20: option_symbol}, settle_time)
    assert trade.status == "CLOSED"
    assert trade.pnl == first_pnl  # PnL was NOT recalculated or altered


# ============================================================================
# 7. Net P&L After Costs Applied Exactly Once
# ============================================================================


def test_pnl_after_costs_applied_exactly_once():
    mapper = PersonalTradeMapper(PnlCalculator())
    calc = costs()

    now = datetime.now(timezone.utc)
    entry_req = option_order(lots=1)
    audit = SimpleNamespace(
        order_source=OrderSource.SYSTEM_SIGNAL,
        override_reason=None,
        premarket_action=RecommendedAction.WATCH,
        prediction_gate=SimpleNamespace(model_dump=lambda mode="json": {}),
    )
    trade = mapper.order_to_entity(entry_req, OPTION, 100.0, calc, audit, TradeType.PAPER)

    # Raw ask: 100.0. Slippage 5 bps -> entry_price: 100.05
    assert trade.entry_price == 100.05
    assert trade.quantity == 65
    entry_fees = trade.tags["entry_fees"]["total_fees"]
    assert entry_fees > 20.0  # Minimum flat brokerage + taxes

    # Exit at 120.0
    mapper.apply_exit(
        trade,
        TradeExitRequest(exit_price=120.0, exit_time=now + timedelta(hours=1), exit_reason="TARGET_HIT"),
        calc,
    )
    assert trade.status == "CLOSED"
    # Slipped exit for SELL leg: 120.0 * (1 - 0.0005) = 119.94
    assert trade.exit_price == 119.94
    exit_fees = trade.tags["exit_fees"]["total_fees"]
    assert exit_fees > 20.0

    # Net PnL = (119.94 - 100.05) * 65 - entry_fees - exit_fees
    expected_gross = (119.94 - 100.05) * 65
    expected_net = round(expected_gross - entry_fees - exit_fees, 2)
    assert trade.pnl == expected_net

    # Attempting to re-close closed trade raises TradeValidationError
    with pytest.raises(TradeValidationError, match="is already closed; duplicate exit prohibited"):
        mapper.apply_exit(
            trade,
            TradeExitRequest(exit_price=120.0, exit_time=now + timedelta(hours=2), exit_reason="TARGET_HIT"),
            calc,
        )


# ============================================================================
# 8. Duplicate Entries and Repeated Signals
# ============================================================================


@pytest.mark.asyncio
async def test_order_service_rejects_duplicate_paper_signal_id():
    repo = FakeRepo()
    service = _setup_service(repo)

    # First placement succeeds
    view1 = await service.place(option_order(), EntryOrigin.AUTO_PAPER, paper_signal_id=555)
    assert view1.id == 1

    # Retry with same paper_signal_id is rejected
    with pytest.raises(TradeValidationError, match="Paper signal 555 has already executed trade 1"):
        await service.place(option_order(), EntryOrigin.AUTO_PAPER, paper_signal_id=555)


@pytest.mark.asyncio
async def test_trade_repository_query_helpers():
    """Verify TradeRepository query helpers with isolated PostgreSQL session."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unreachable: {type(exc).__name__}")

    schema = f"test_repo_helpers_{uuid.uuid4().hex[:12]}"
    await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    await conn.execute(text(f'SET search_path TO "{schema}"'))
    await conn.run_sync(Base.metadata.create_all)
    await conn.commit()

    session = AsyncSession(bind=conn, expire_on_commit=False)
    repo = TradeRepository(session)
    now = datetime.now(timezone.utc)

    try:
        t1 = Trade(
            symbol="NIFTY27OCT2625000CE", action="BUY", trade_type="PAPER",
            status="OPEN", entry_price=100.0, quantity=65, invested_amount=6500.0,
            entry_time=now, paper_signal_id=777, order_source="SYSTEM_SIGNAL",
        )
        await repo.add(t1)
        await session.commit()

        # Check get_by_paper_signal_id
        found = await repo.get_by_paper_signal_id(777)
        assert found is not None
        assert found.id == t1.id

        not_found = await repo.get_by_paper_signal_id(888)
        assert not_found is None

        # Check has_open_for_symbol
        assert await repo.has_open_for_symbol("NIFTY27OCT2625000CE") is True
        assert await repo.has_open_for_symbol("NIFTY27OCT2625100CE") is False

        # Check count_open_by_underlying with robust parser
        assert await repo.count_open_by_underlying(OptionUnderlying.NIFTY) == 1
        assert await repo.count_open_by_underlying(OptionUnderlying.BANKNIFTY) == 0
        assert await repo.count_open_by_underlying(OptionUnderlying.SENSEX) == 0

        # Add BANKNIFTY trade and check separation
        t2 = Trade(
            symbol="BANKNIFTY27OCT2652000CE", action="BUY", trade_type="PAPER",
            status="OPEN", entry_price=200.0, quantity=30, invested_amount=6000.0,
            entry_time=now, paper_signal_id=778, order_source="SYSTEM_SIGNAL",
        )
        await repo.add(t2)
        await session.commit()
        assert await repo.count_open_by_underlying(OptionUnderlying.NIFTY) == 1
        assert await repo.count_open_by_underlying(OptionUnderlying.BANKNIFTY) == 1
    finally:
        await session.close()
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await conn.commit()
        await conn.close()
        await engine.dispose()


@asynccontextmanager
async def _schema_isolated_engine():
    root_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    schema = f"test_iso_{uuid.uuid4().hex[:8]}"
    try:
        async with root_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    except Exception as exc:
        await root_engine.dispose()
        pytest.skip(f"Postgres unreachable: {type(exc).__name__}")

    schema_engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with schema_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield schema_engine, schema
    finally:
        await schema_engine.dispose()
        async with root_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root_engine.dispose()


@pytest.mark.asyncio
async def test_database_enforces_paper_signal_unique_constraint():
    """Verify that PostgreSQL unique index uq_trades_paper_signal_id strictly prevents duplicates."""
    async with _schema_isolated_engine() as (schema_engine, _):
        now = datetime.now(timezone.utc)

        # Session 1: insert trade with paper_signal_id=9999
        async with AsyncSession(schema_engine, expire_on_commit=False) as session1:
            repo1 = TradeRepository(session1)
            t1 = Trade(
                symbol=OPTION.symbol, action="BUY", trade_type="PAPER",
                status="OPEN", entry_price=100.0, quantity=65, invested_amount=6500.0,
                entry_time=now, paper_signal_id=9999, order_source="SYSTEM_SIGNAL",
            )
            await repo1.add(t1)
            await session1.commit()

        # Session 2: try to insert duplicate trade with paper_signal_id=9999
        with pytest.raises(Exception) as excinfo:
            async with AsyncSession(schema_engine, expire_on_commit=False) as session2:
                repo2 = TradeRepository(session2)
                t2 = Trade(
                    symbol=OPTION.symbol, action="BUY", trade_type="PAPER",
                    status="OPEN", entry_price=105.0, quantity=65, invested_amount=6800.0,
                    entry_time=now, paper_signal_id=9999, order_source="SYSTEM_SIGNAL",
                )
                await repo2.add(t2)
                await session2.commit()
        assert "uq_trades_paper_signal_id" in str(excinfo.value) or "unique" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_concurrent_order_placement_same_paper_signal_separate_sessions():
    """Verify concurrent OrderService.place attempts across separate PostgreSQL sessions."""
    async with _schema_isolated_engine() as (schema_engine, _):
        async def _attempt_place(client_id: int):
            async with AsyncSession(schema_engine, expire_on_commit=False) as session_i:
                try:
                    repo_i = TradeRepository(session_i)
                    calendar = ScriptedCalendar(REGULAR_SESSION)
                    premarket = FakePremarket(RecommendedAction.WATCH)
                    predictions = FakePredictions(OPTION.symbol, GateReason.NONE)
                    entry_gates = gates(calendar, premarket, predictions)
                    service = order_service(repo_i, OPTION, entry_gates, ltp=100.0)

                    # Attempt placement with paper_signal_id=1234
                    res = await service.place(option_order(), EntryOrigin.AUTO_PAPER, paper_signal_id=1234)
                    await session_i.commit()
                    return ("SUCCESS", res.id)
                except Exception as exc:
                    await session_i.rollback()
                    return ("FAILED", type(exc).__name__, str(exc))

        # Launch 5 concurrent placement attempts with the same paper_signal_id
        outcomes = await asyncio.gather(*(_attempt_place(i) for i in range(5)))
        successes = [o for o in outcomes if o[0] == "SUCCESS"]
        failures = [o for o in outcomes if o[0] == "FAILED"]

        # Exactly 1 must succeed, exactly 4 must fail
        assert len(successes) == 1
        assert len(failures) == 4
        for f in failures:
            assert f[1] in ("TradeValidationError", "IntegrityError")


@pytest.mark.asyncio
async def test_concurrent_order_placement_max_positions_limit():
    """Verify concurrent orders cannot bypass risk_max_open_positions cap."""
    async with _schema_isolated_engine() as (schema_engine, _):
        now = datetime.now(timezone.utc)
        max_positions = settings.risk_max_open_positions

        # Pre-populate max_positions - 1 open trades
        async with AsyncSession(schema_engine, expire_on_commit=False) as setup_session:
            setup_repo = TradeRepository(setup_session)
            for i in range(max_positions - 1):
                t = Trade(
                    symbol=f"STOCK_{i}.NS", action="BUY", trade_type="PAPER",
                    status="OPEN", entry_price=100.0, quantity=10, invested_amount=1000.0,
                    entry_time=now, paper_signal_id=1000 + i, order_source="SYSTEM_SIGNAL",
                )
                await setup_repo.add(t)
            await setup_session.commit()

        async def _attempt_competing_place(idx: int):
            async with AsyncSession(schema_engine, expire_on_commit=False) as session_i:
                try:
                    repo_i = TradeRepository(session_i)
                    calendar = ScriptedCalendar(REGULAR_SESSION)
                    premarket = FakePremarket(RecommendedAction.WATCH)
                    predictions = FakePredictions(OPTION.symbol, GateReason.NONE)
                    entry_gates = gates(calendar, premarket, predictions)
                    service = order_service(repo_i, OPTION, entry_gates, ltp=100.0)

                    # Each task tries a unique paper_signal_id
                    res = await service.place(option_order(), EntryOrigin.AUTO_PAPER, paper_signal_id=2000 + idx)
                    await session_i.commit()
                    return ("SUCCESS", res.id)
                except Exception as exc:
                    await session_i.rollback()
                    return ("FAILED", type(exc).__name__, str(exc))

        # 4 concurrent placement attempts competing for the 1 remaining slot
        outcomes = await asyncio.gather(*(_attempt_competing_place(i) for i in range(4)))
        successes = [o for o in outcomes if o[0] == "SUCCESS"]
        failures = [o for o in outcomes if o[0] == "FAILED"]

        # Exactly 1 must take the last slot, 3 must be blocked by position cap
        assert len(successes) == 1
        assert len(failures) == 3
        for f in failures:
            assert f[1] == "TradeValidationError"
            assert "Maximum open positions reached" in f[2]


# These two tests run RiskMonitor against the real wall clock, so the contract must not be
# expired at run time (the 27 Oct 2026 OPTION fixture would settle as EXPIRED, not SL_HIT).
UNEXPIRED_OPTION_SYMBOL = "NIFTY28DEC6825000CE"  # expires 2068-12-28


@pytest.mark.asyncio
async def test_risk_monitor_persists_and_restores_unresolved_exposure_across_restart():
    """Verify that unresolved exposure is persisted to PostgreSQL and restored upon process restart."""
    async with _schema_isolated_engine() as (schema_engine, _):
        now = datetime.now(timezone.utc)

        # 1. Create open trade with stop loss in PostgreSQL
        async with AsyncSession(schema_engine, expire_on_commit=False) as session1:
            repo1 = TradeRepository(session1)
            trade = Trade(
                symbol=UNEXPIRED_OPTION_SYMBOL, action="BUY", trade_type="PAPER",
                status="OPEN", entry_price=100.0, quantity=65, invested_amount=6520.0,
                stop_loss=90.0, target_1=120.0, entry_time=now - timedelta(minutes=20),
                order_source="SYSTEM_SIGNAL", tags={"entry_fees": {"total_fees": 21.0}},
            )
            await repo1.add(trade)
            await session1.commit()
            trade_id = trade.id

        # 2. RiskMonitor runs with STALE quote -> must defer exit and persist unresolved exposure to trade.tags
        stale_ts = now - timedelta(seconds=60)
        stale_tick = Tick(
            symbol=UNEXPIRED_OPTION_SYMBOL, ltp=85.0, prev_close=100.0, change=-15.0, change_pct=-15.0,
            timestamp=now, provider="ANGEL", fetched_at=now, exchange_timestamp=stale_ts,
        )

        @asynccontextmanager
        async def _session_factory():
            async with AsyncSession(schema_engine, expire_on_commit=False) as s:
                yield s

        monitor1 = RiskMonitor(
            market_data=FakeMarketData(stale_tick),
            evaluator=StopTargetEvaluator(),
            contracts=FakeContractResolver(),
            expiry_policy=ExpirySettlementPolicy(),
            mapper=PersonalTradeMapper(PnlCalculator()),
            costs=costs(),
            interval_seconds=60,
            session_factory=_session_factory,
        )
        await monitor1.check_once()

        # Verify trade remains OPEN in DB and trade.tags has unresolved_exposure
        async with AsyncSession(schema_engine, expire_on_commit=False) as s_verify:
            t_after_defer = await s_verify.get(Trade, trade_id)
            assert t_after_defer.status == "OPEN"
            assert "unresolved_exposure" in t_after_defer.tags
            assert "Quote stale" in t_after_defer.tags["unresolved_exposure"]["reason"]

        # 3. Process restart simulation: Create a brand new RiskMonitor instance with a FRESH quote
        fresh_tick = Tick(
            symbol=UNEXPIRED_OPTION_SYMBOL, ltp=85.0, prev_close=100.0, change=-15.0, change_pct=-15.0,
            timestamp=now, provider="ANGEL", fetched_at=now, exchange_timestamp=now,
        )
        monitor_restarted = RiskMonitor(
            market_data=FakeMarketData(fresh_tick),
            evaluator=StopTargetEvaluator(),
            contracts=FakeContractResolver(),
            expiry_policy=ExpirySettlementPolicy(),
            mapper=PersonalTradeMapper(PnlCalculator()),
            costs=costs(),
            interval_seconds=60,
            session_factory=_session_factory,
        )
        # Run check_once on restarted monitor: it restores unresolved exposure, sees fresh quote, executes SL exit, and clears exposure
        await monitor_restarted.check_once()

        async with AsyncSession(schema_engine, expire_on_commit=False) as s_final:
            t_final = await s_final.get(Trade, trade_id)
            assert t_final.status == "CLOSED"
            assert t_final.exit_reason == "SL_HIT"
            assert "unresolved_exposure" not in t_final.tags  # Cleared from DB!
            assert trade_id not in monitor_restarted.unresolved_exposures


@pytest.mark.asyncio
async def test_concurrent_risk_monitor_check_once_does_not_double_close():
    """Verify concurrent monitor check_once runs on separate sessions do not close the trade twice."""
    async with _schema_isolated_engine() as (schema_engine, _):
        now = datetime.now(timezone.utc)

        # Create open trade hitting stop loss
        async with AsyncSession(schema_engine, expire_on_commit=False) as session1:
            repo1 = TradeRepository(session1)
            trade = Trade(
                symbol=UNEXPIRED_OPTION_SYMBOL, action="BUY", trade_type="PAPER",
                status="OPEN", entry_price=100.0, quantity=65, invested_amount=6520.0,
                stop_loss=90.0, target_1=120.0, entry_time=now - timedelta(minutes=20),
                order_source="SYSTEM_SIGNAL", tags={"entry_fees": {"total_fees": 21.0}},
            )
            await repo1.add(trade)
            await session1.commit()
            trade_id = trade.id

        fresh_tick = Tick(
            symbol=UNEXPIRED_OPTION_SYMBOL, ltp=85.0, prev_close=100.0, change=-15.0, change_pct=-15.0,
            timestamp=now, provider="ANGEL", fetched_at=now, exchange_timestamp=now,
        )

        def _make_monitor():
            @asynccontextmanager
            async def _session_factory():
                async with AsyncSession(schema_engine, expire_on_commit=False) as s:
                    yield s

            return RiskMonitor(
                market_data=FakeMarketData(fresh_tick),
                evaluator=StopTargetEvaluator(),
                contracts=FakeContractResolver(),
                expiry_policy=ExpirySettlementPolicy(),
                mapper=PersonalTradeMapper(PnlCalculator()),
                costs=costs(),
                interval_seconds=60,
                session_factory=_session_factory,
            )

        mon1 = _make_monitor()
        mon2 = _make_monitor()

        # Run 2 monitors concurrently
        await asyncio.gather(mon1.check_once(), mon2.check_once())

        # Verify trade is closed once and fees are not double applied
        async with AsyncSession(schema_engine, expire_on_commit=False) as s_verify:
            t = await s_verify.get(Trade, trade_id)
            assert t.status == "CLOSED"
            assert t.exit_reason == "SL_HIT"
            # Exit fees applied exactly once:
            assert "exit_fees" in t.tags
            assert isinstance(t.tags["exit_fees"], dict)
            assert t.pnl is not None


