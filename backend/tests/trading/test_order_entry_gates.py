"""
Regression tests for OrderService.place entry gates.
Supersedes the characterization of the pre-change behaviour (flag-controlled NO_TRADE,
WAIT ignored, no session check, order_source silently ignored).
"""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from schemas.order_entry import OVERRIDE_REASON_MAX_LENGTH, EntryOrigin, OrderSource
from schemas.personal_trade import TradeType
from schemas.prediction import GateReason
from schemas.premarket import RecommendedAction
from schemas.trading import MarketOrderRequest, Tick
from services.options.expiry_settlement_policy import ExpirySettlementPolicy
from services.personal.errors import TradeValidationError
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.risk_monitor import RiskMonitor
from services.trading.stop_target_evaluator import StopTargetEvaluator
from services.risk.daily_risk_state import DailyRiskState
from services.risk.pre_trade_risk_gate import PreTradeRiskGate
from services.trading.order_service import OrderService
from services.trading.order_validator import OrderValidator
from order_entry_fakes import (
    AFTER_HOURS,
    FakeContractResolver,
    HOLIDAY,
    OPTION,
    OTHER_OPTION_SYMBOL,
    PREMARKET_SESSION,
    REGULAR_SESSION,
    SPECIAL_DAY,
    STOCK,
    WEEKEND,
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

REASON = "Breakout confirmed on 5m with volume"


def _stock_service(action, repo, *moments):
    calendar = ScriptedCalendar(*(moments or (REGULAR_SESSION,)))
    return order_service(repo, STOCK, gates(calendar, FakePremarket(action), FakePredictions(OPTION.symbol)))


def _option_service(action, repo, predictions, ltp=100.0):
    return order_service(
        repo, OPTION, gates(ScriptedCalendar(REGULAR_SESSION), FakePremarket(action), predictions), ltp=ltp
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", list(EntryOrigin))
@pytest.mark.parametrize("reason", [None, REASON])
async def test_no_trade_blocks_every_entry_unconditionally(origin, reason):
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match="NO_TRADE"):
        await _stock_service(RecommendedAction.NO_TRADE, repo).place(stock_order(override_reason=reason), origin)
    assert repo.added == []


@pytest.mark.asyncio
async def test_wait_without_reason_is_rejected():
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match="WAIT"):
        await _stock_service(RecommendedAction.WAIT, repo).place(stock_order(), EntryOrigin.API)
    assert repo.added == []


@pytest.mark.asyncio
async def test_wait_with_reason_is_manual_override_and_audited():
    repo = FakeRepo()
    view = await _stock_service(RecommendedAction.WAIT, repo).place(
        stock_order(override_reason=f"  {REASON}  "), EntryOrigin.API
    )
    trade = repo.added[0]
    assert view.order_source == OrderSource.MANUAL_OVERRIDE
    assert trade.order_source == OrderSource.MANUAL_OVERRIDE.value
    assert trade.override_reason == REASON
    assert trade.premarket_action_at_entry == RecommendedAction.WAIT.value
    assert trade.prediction_gate_at_entry["available"] is False


@pytest.mark.asyncio
async def test_wait_blocks_strategy_entries():
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match="WAIT"):
        await _stock_service(RecommendedAction.WAIT, repo).place(stock_order(), EntryOrigin.ORB_STRATEGY)
    assert repo.added == []


@pytest.mark.asyncio
async def test_override_does_not_bypass_risk_checks():
    repo = FakeRepo()
    oversized_stop = stock_order(override_reason=REASON).model_copy(update={"stop_loss": 1.0, "lots": 500})
    with pytest.raises(TradeValidationError, match="risk"):
        await _stock_service(RecommendedAction.WAIT, repo).place(oversized_stop, EntryOrigin.API)
    assert repo.added == []


@pytest.mark.asyncio
async def test_watch_signal_match_is_system_signal_with_snapshot():
    repo = FakeRepo()
    predictions = FakePredictions(OPTION.symbol)
    view = await _option_service(RecommendedAction.WATCH, repo, predictions).place(option_order(), EntryOrigin.API)
    trade = repo.added[0]
    assert view.order_source == OrderSource.SYSTEM_SIGNAL
    assert trade.override_reason is None
    assert trade.prediction_gate_at_entry["contract_symbol"] == OPTION.symbol
    assert trade.prediction_gate_at_entry["gate_reason"] == GateReason.NONE.value
    assert predictions.calls == 1


@pytest.mark.asyncio
async def test_watch_signal_match_with_reason_is_inconsistent():
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match="inconsistent"):
        await _option_service(RecommendedAction.WATCH, repo, FakePredictions(OPTION.symbol)).place(
            option_order(override_reason=REASON), EntryOrigin.API
        )
    assert repo.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "predictions",
    [
        FakePredictions(OTHER_OPTION_SYMBOL),
        FakePredictions(OPTION.symbol, GateReason.MTF_CONFLICT),
        FakePredictions(None),
    ],
    ids=["different-contract", "gated-prediction", "prediction-error"],
)
async def test_watch_non_signal_requires_reason(predictions):
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match="does not match"):
        await _option_service(RecommendedAction.WATCH, repo, predictions).place(option_order(), EntryOrigin.API)
    assert repo.added == []


@pytest.mark.asyncio
async def test_watch_non_signal_with_reason_is_manual_override():
    repo = FakeRepo()
    view = await _stock_service(RecommendedAction.WATCH, repo).place(
        stock_order(override_reason=REASON), EntryOrigin.API
    )
    assert view.order_source == OrderSource.MANUAL_OVERRIDE
    assert repo.added[0].prediction_gate_at_entry["note"] == "No prediction for non-option instruments"


@pytest.mark.asyncio
async def test_strategy_entry_is_system_signal_without_prediction_lookup():
    repo = FakeRepo()
    predictions = FakePredictions(OTHER_OPTION_SYMBOL)
    view = await _option_service(RecommendedAction.WATCH, repo, predictions).place(
        option_order(), EntryOrigin.ORB_STRATEGY
    )
    assert view.order_source == OrderSource.SYSTEM_SIGNAL
    assert predictions.calls == 0


@pytest.mark.asyncio
async def test_strategy_entry_rejects_override_reason():
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match="Strategy"):
        await _stock_service(RecommendedAction.WATCH, repo).place(
            stock_order(override_reason=REASON), EntryOrigin.ORB_STRATEGY
        )


@pytest.mark.asyncio
async def test_premarket_failure_blocks_entry():
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match="Pre-market state unavailable"):
        await _stock_service(None, repo).place(stock_order(override_reason=REASON), EntryOrigin.API)
    assert repo.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "moment, phase",
    [
        (WEEKEND, "HOLIDAY_OR_WEEKEND"),
        (HOLIDAY, "HOLIDAY_OR_WEEKEND"),
        (PREMARKET_SESSION, "PRE_OPEN"),
        (AFTER_HOURS, "POST_CLOSE"),
    ],
    ids=["weekend", "holiday", "premarket", "after-hours"],
)
async def test_closed_session_rejects_entry(moment, phase):
    repo = FakeRepo()
    with pytest.raises(TradeValidationError, match=phase):
        await _stock_service(RecommendedAction.WATCH, repo, moment).place(
            stock_order(override_reason=REASON), EntryOrigin.API
        )
    assert repo.added == []


@pytest.mark.asyncio
async def test_configured_special_session_allows_entry():
    repo = FakeRepo()
    await _stock_service(RecommendedAction.WATCH, repo, SPECIAL_DAY).place(
        stock_order(override_reason=REASON), EntryOrigin.API
    )
    assert len(repo.added) == 1


@pytest.mark.asyncio
async def test_session_is_revalidated_immediately_before_persist():
    repo = FakeRepo()
    service = _stock_service(RecommendedAction.WATCH, repo, REGULAR_SESSION, AFTER_HOURS)
    with pytest.raises(TradeValidationError, match="POST_CLOSE"):
        await service.place(stock_order(override_reason=REASON), EntryOrigin.API)
    assert repo.added == []


def test_client_cannot_set_order_source():
    with pytest.raises(ValidationError, match="order_source"):
        MarketOrderRequest(symbol=STOCK.symbol, action="BUY", lots=1, order_source="SYSTEM_SIGNAL")


@pytest.mark.parametrize("reason", ["", "   ", "x" * (OVERRIDE_REASON_MAX_LENGTH + 1)])
def test_override_reason_validation_rejects(reason):
    with pytest.raises(ValidationError):
        MarketOrderRequest(symbol=STOCK.symbol, action="BUY", lots=1, override_reason=reason)


def test_override_reason_is_trimmed_and_max_length_accepted():
    request = MarketOrderRequest(
        symbol=STOCK.symbol, action="BUY", lots=1, override_reason=" " + "x" * OVERRIDE_REASON_MAX_LENGTH + " "
    )
    assert request.override_reason == "x" * OVERRIDE_REASON_MAX_LENGTH


@pytest.mark.asyncio
async def test_manual_exit_is_exempt_from_premarket_and_session_gates():
    repo = FakeRepo()
    entry = _stock_service(RecommendedAction.WATCH, repo)
    await entry.place(stock_order(override_reason=REASON), EntryOrigin.API)
    repo.added[0].trade_type = TradeType.MANUAL.value
    premarket = FakePremarket(RecommendedAction.NO_TRADE)
    closed = order_service(
        repo, STOCK, gates(ScriptedCalendar(WEEKEND), premarket, FakePredictions(OPTION.symbol))
    )
    await closed.exit(1)
    assert repo.added[0].status == "CLOSED"
    assert premarket.calls == 0


@pytest.mark.asyncio
async def test_stop_loss_exit_is_exempt_from_entry_gates():
    repo = FakeRepo()
    await _stock_service(RecommendedAction.WATCH, repo).place(stock_order(override_reason=REASON), EntryOrigin.API)
    monitor = RiskMonitor(
        market_data=FakeMarketData(tick(STOCK.symbol, ltp=990.0)),
        evaluator=StopTargetEvaluator(),
        contracts=FakeContractResolver(),
        expiry_policy=ExpirySettlementPolicy(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        costs=costs(),
        interval_seconds=60,
    )
    await monitor._apply_stops(repo.added, WEEKEND)
    assert repo.added[0].status == "CLOSED"
    assert repo.added[0].exit_reason == "SL_HIT"


@pytest.mark.asyncio
async def test_order_placement_blocked_if_tick_lacks_exchange_timestamp():
    repo = FakeRepo()
    now = datetime.now(timezone.utc)
    yahoo_tick = Tick(
        symbol=STOCK.symbol, ltp=1000.0, prev_close=1000.0, change=0.0, change_pct=0.0,
        timestamp=now, provider="YAHOO", fetched_at=now, exchange_timestamp=None,
    )
    calculator = costs()
    service = OrderService(
        repository=repo,
        resolver=FakeResolver(STOCK),
        market_data=FakeMarketData(yahoo_tick),
        validator=OrderValidator(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        risk_gate=PreTradeRiskGate(30, 1.0, 3.0, 5, calculator),
        costs=calculator,
        daily_risk=DailyRiskState(),
        gates=gates(ScriptedCalendar(REGULAR_SESSION), FakePremarket(RecommendedAction.WATCH), FakePredictions(OPTION.symbol)),
    )
    with pytest.raises(TradeValidationError, match="Missing verified exchange timestamp"):
        await service.place(stock_order(override_reason=REASON), EntryOrigin.API)
    assert repo.added == []


@pytest.mark.asyncio
async def test_order_placement_blocked_if_exchange_timestamp_is_stale():
    repo = FakeRepo()
    now = datetime.now(timezone.utc)
    stale_exchange = now - timedelta(seconds=120)
    stale_tick = Tick(
        symbol=STOCK.symbol, ltp=1000.0, prev_close=1000.0, change=0.0, change_pct=0.0,
        timestamp=stale_exchange, provider="ANGEL", fetched_at=now, exchange_timestamp=stale_exchange,
    )
    calculator = costs()
    service = OrderService(
        repository=repo,
        resolver=FakeResolver(STOCK),
        market_data=FakeMarketData(stale_tick),
        validator=OrderValidator(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        risk_gate=PreTradeRiskGate(30, 1.0, 3.0, 5, calculator),
        costs=calculator,
        daily_risk=DailyRiskState(),
        gates=gates(ScriptedCalendar(REGULAR_SESSION), FakePremarket(RecommendedAction.WATCH), FakePredictions(OPTION.symbol)),
    )
    with pytest.raises(TradeValidationError, match="Exchange data stale.*risk_max_data_age_seconds=30s"):
        await service.place(stock_order(override_reason=REASON), EntryOrigin.API)
    assert repo.added == []
