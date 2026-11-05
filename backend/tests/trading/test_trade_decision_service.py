import asyncio
import time
from datetime import date
from types import SimpleNamespace

import pytest

from schemas.options import OptionUnderlying
from schemas.prediction import DataFreshness, FreshnessBasis, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction
from schemas.trade_decision import TradeDecisionBlockCode, TradeDecisionStatus
from services.risk.daily_risk_state import DailyRiskState
from services.trading.entry_session_gate import EntrySessionGate
from services.trading.trade_decision_evaluator import TradeDecisionEvaluator
from services.trading.trade_decision_service import TradeDecisionService
from tests.premarket.test_trading_calendar import FixedCalendar
from tests.trading.order_entry_fakes import AFTER_HOURS, REGULAR_SESSION


class _Predictions:
    def __init__(self, delay: float = 0.0, error: bool = False):
        self.delay = delay
        self.error = error
        self.calls = 0

    async def predict(self, underlying, expiry, session=None, force=False):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise RuntimeError("chain down")
        return SimpleNamespace(
            direction=PredictionDirection.CALL,
            gate_reason=GateReason.NONE,
            data_freshness=DataFreshness.FRESH,
            contract=SimpleNamespace(quote=SimpleNamespace(symbol="NIFTY27OCT2625000CE")),
            quote_timestamps=[
                SimpleNamespace(verified=True, basis=FreshnessBasis.EXCHANGE)
            ],
        )


class _Premarket:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls = 0

    async def analyze(self, force=False):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return SimpleNamespace(recommended_action=RecommendedAction.WATCH)


class _RepoSession:
    """Minimal stand-in: TradeRepository methods are patched via FakeRepo-like session unused."""


class _Repo:
    async def realized_pnl_on(self, day):
        return 0.0

    async def count_open(self):
        return 0

    async def list_open(self, trade_type=None):
        return []


@pytest.fixture
def patch_repo(monkeypatch):
    monkeypatch.setattr(
        "services.trading.trade_decision_service.TradeRepository",
        lambda session: _Repo(),
    )


def _service(calendar_moment, predictions, premarket) -> TradeDecisionService:
    calendar = FixedCalendar(calendar_moment, frozenset())
    return TradeDecisionService(
        predictions=predictions,
        premarket=premarket,
        session_gate=EntrySessionGate(calendar),
        evaluator=TradeDecisionEvaluator(),
        daily_risk=DailyRiskState(),
        max_open_positions=5,
        daily_loss_limit_pct=3.0,
        starting_capital=100000.0,
    )


@pytest.mark.asyncio
async def test_prediction_error_fail_closes_without_raising(patch_repo):
    service = _service(REGULAR_SESSION, _Predictions(error=True), _Premarket())
    result = await service.evaluate(OptionUnderlying.NIFTY, date(2026, 10, 27), session=object())
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.block_code == TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE
    assert result.data_freshness == DataFreshness.NOT_EVALUATED


@pytest.mark.asyncio
async def test_prediction_timeout_fail_closes(patch_repo, monkeypatch):
    monkeypatch.setattr(
        "services.trading.trade_decision_service.DECISION_COMPONENT_TIMEOUT_SECONDS",
        0.05,
    )
    service = _service(REGULAR_SESSION, _Predictions(delay=1.0), _Premarket())
    result = await service.evaluate(OptionUnderlying.NIFTY, date(2026, 10, 27), session=object())
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.block_code == TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE
    assert result.data_freshness == DataFreshness.NOT_EVALUATED


@pytest.mark.asyncio
async def test_premarket_and_prediction_run_in_parallel(patch_repo):
    predictions = _Predictions(delay=0.15)
    premarket = _Premarket(delay=0.15)
    service = _service(AFTER_HOURS, predictions, premarket)
    started = time.monotonic()
    result = await service.evaluate(OptionUnderlying.NIFTY, date(2026, 10, 27), session=object())
    elapsed = time.monotonic() - started
    assert elapsed < 0.28
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.block_code == TradeDecisionBlockCode.SESSION_CLOSED
    assert predictions.calls == 1
    assert premarket.calls == 1
