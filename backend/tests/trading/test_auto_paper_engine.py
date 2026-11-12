"""AutoPaperEngine rules with fakes: entry window, dedupe, daily cap, fill/gate rejections, square-off."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytz

from schemas.options import OptionQuote, OptionType, OptionUnderlying
from schemas.paper_engine import AutoPaperConfig, PaperExecutionStatus, PaperSignalEligibility
from schemas.prediction import (
    DataFreshness,
    GateReason,
    OptionPrediction,
    PredictionDirection,
    PremiumLevels,
    SuggestedContract,
)
from schemas.trading import ExitReason, Tick
from services.costs.paper_cost_calculator import PaperCostCalculator
from schemas.costs import CostConfig
from services.personal.errors import TradeValidationError
from services.trading.auto_paper_engine import AutoPaperEngine, is_auto_trade_for
from services.trading.paper_fill_model import PaperFillModel

IST = pytz.timezone("Asia/Kolkata")
SYMBOL = "NIFTY17NOV2625300CE"
COSTS = PaperCostCalculator(CostConfig(brokerage_pct=0.03, brokerage_flat=20, exchange_txn_pct=0.00345,
                                       sebi_pct=0.0001, stamp_duty_buy_pct=0.015, stt_sell_pct=0.025,
                                       gst_pct=18, slippage_bps=5))


def at(hh, mm):
    return IST.localize(datetime(2026, 11, 13, hh, mm)).astimezone(timezone.utc)


def quote(now, bid=99.0, ask=100.0, volume=1000.0, age=2):
    return OptionQuote.model_construct(
        symbol=SYMBOL, display_name="NIFTY 25300 CE", ltp=100.0, change=0, change_pct=0, open_interest=5000,
        volume=volume, bid=bid, ask=ask, fetched_at=now, exchange_timestamp=now - timedelta(seconds=age),
    )


def prediction(now, direction=PredictionDirection.CALL, gate=GateReason.NONE, with_contract=True, **quote_kw):
    contract = None
    if with_contract:
        contract = SuggestedContract.model_construct(
            strike=25300.0, option_type=OptionType.CE, quote=quote(now, **quote_kw),
            levels=PremiumLevels(entry=100.0, stop_loss=80.0, target=140.0),
        )
    return OptionPrediction.model_construct(
        underlying=OptionUnderlying.NIFTY, expiry=date(2026, 11, 17), spot=25300.0, lot_size=65,
        direction=direction, score=0.4, raw_score=0.4, signal_score=70.0, confidence=70.0,
        gate_reason=gate, data_freshness=DataFreshness.FRESH, contract=contract, generated_at=now,
        log_id=1, premarket_action="WATCH", premarket_wait_trigger="NONE",
    )


class Calendar:
    def __init__(self, phase="REGULAR"):
        self.phase = phase

    def session_phase(self, _):
        return self.phase


class Predictions:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def predict(self, underlying, expiry, session=None):
        self.calls.append((underlying, expiry, session))
        return self.result


class World:
    """Shared fake database state across units."""

    def __init__(self):
        self.signals = []
        self.trades = []
        self.placed = []
        self.closed = []
        self.place_error = None
        self.commits = 0


class FakeUnit:
    def __init__(self, world: World):
        self.world = world
        self.session = "SESSION"
        self._pending = []

    async def open_auto_trades(self, for_update=False):
        return [t for t in self.world.trades if t.status == "OPEN" and t.paper_signal_id is not None]

    async def entries_on(self, underlying, day):
        return sum(1 for s in self.world.signals if s["execution_status"] == PaperExecutionStatus.EXECUTED)

    async def add_signal(self, data):
        record = {"id": len(self.world.signals) + 1, **data.model_dump()}
        self._pending.append(record)
        return record["id"]

    async def update_signal(self, signal_id, **changes):
        for s in self._pending + self.world.signals:
            if s["id"] == signal_id:
                s.update({k: v for k, v in changes.items() if k != "event"})

    async def place(self, request, signal_id):
        if self.world.place_error:
            raise self.world.place_error
        trade = SimpleNamespace(id=len(self.world.trades) + 1, symbol=request.symbol, status="OPEN",
                                paper_signal_id=signal_id, entry_price=100.0, quantity=request.lots * 65)
        self.world.placed.append((request, signal_id))
        self._pending_trade = trade
        return trade

    async def close_trade(self, trade, exit_price, at_, reason):
        trade.status = "CLOSED"
        self.world.closed.append((trade.id, exit_price, reason))

    async def commit(self):
        self.world.signals.extend(self._pending)
        self._pending = []
        if getattr(self, "_pending_trade", None) is not None:
            self.world.trades.append(self._pending_trade)
            self._pending_trade = None
        self.world.commits += 1

    async def rollback(self):
        self._pending = []
        self._pending_trade = None


def engine(world, predictions, now, phase="REGULAR", ticks=None, **cfg):
    config = dict(enabled=True, underlyings=[OptionUnderlying.NIFTY], interval_seconds=60, lots=1,
                  entry_start="09:20", last_entry="15:00", square_off="15:15", max_entries_per_day=5,
                  repeat_rejection_minutes=15)
    config.update(cfg)

    @asynccontextmanager
    async def units():
        yield FakeUnit(world)

    async def expiries(_):
        return [date(2026, 11, 17)]

    async def quotes(symbols):
        return {s: t for s, t in (ticks or {}).items() if s in symbols}

    return AutoPaperEngine(
        config=AutoPaperConfig(**config), calendar=Calendar(phase), predictions=predictions,
        expiries=expiries, units=units, fill_model=PaperFillModel(COSTS), quotes=quotes,
        scorer_version="v1.3_freshness", clock=lambda: now,
    )


# ── entries ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_actionable_signal_places_one_paper_buy_through_order_service():
    now, world = at(10, 0), World()
    preds = Predictions(prediction(at(10, 0)))
    note = await engine(world, preds, now).check_once()
    assert "paper BUY" in note
    request, signal_id = world.placed[0]
    assert request.symbol == SYMBOL and request.lots == 1
    assert request.stop_loss == 80.0 and request.target == 140.0
    assert preds.calls[0][2] == "SESSION"                    # prediction logged in a DB session
    signal = world.signals[0]
    assert signal["execution_status"] == PaperExecutionStatus.EXECUTED and signal["trade_id"] == 1
    assert signal["strategy"] == "AUTO_OPTION_PREDICTION"


@pytest.mark.asyncio
@pytest.mark.parametrize("clock, phase", [((9, 19), "REGULAR"), ((15, 0), "REGULAR"), ((10, 0), "PRE_OPEN"),
                                          ((10, 0), "HOLIDAY_OR_WEEKEND")])
async def test_no_entries_outside_window_or_session(clock, phase):
    now, world = at(*clock), World()
    preds = Predictions(prediction(now))
    await engine(world, preds, now, phase=phase).check_once()
    assert world.placed == [] and world.signals == [] and preds.calls == []


@pytest.mark.asyncio
async def test_disabled_engine_does_nothing():
    now, world = at(10, 0), World()
    assert await engine(world, Predictions(prediction(now)), now, enabled=False).check_once() == "disabled"
    assert world.placed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("direction, gate, with_contract", [
    (PredictionDirection.WAIT, GateReason.NONE, False),
    (PredictionDirection.NO_TRADE, GateReason.NONE, False),
    (PredictionDirection.CALL, GateReason.EXPIRY_PRE_CLOSE, True),
    (PredictionDirection.CALL, GateReason.NONE, False),
])
async def test_non_actionable_predictions_place_nothing(direction, gate, with_contract):
    now, world = at(10, 0), World()
    await engine(world, Predictions(prediction(now, direction, gate, with_contract)), now).check_once()
    assert world.placed == [] and world.signals == []


@pytest.mark.asyncio
async def test_one_open_auto_position_per_underlying():
    now, world = at(10, 0), World()
    e = engine(world, Predictions(prediction(now)), now)
    await e.check_once()
    note = await e.check_once()
    assert len(world.placed) == 1 and "already open" in note


@pytest.mark.asyncio
async def test_daily_entry_cap():
    now, world = at(10, 0), World()
    e = engine(world, Predictions(prediction(now)), now, max_entries_per_day=1)
    await e.check_once()
    world.trades[0].status = "CLOSED"                        # e.g. stop loss hit
    note = await e.check_once()
    assert len(world.placed) == 1 and "limit 1 reached" in note


@pytest.mark.asyncio
async def test_wide_spread_is_rejected_before_any_order():
    now, world = at(10, 0), World()
    await engine(world, Predictions(prediction(now, bid=80.0, ask=100.0)), now).check_once()
    assert world.placed == []
    assert world.signals[0]["eligibility_status"] == PaperSignalEligibility.REJECTED_FILL
    assert any("spread too wide" in r for r in world.signals[0]["rejection_reasons"])


@pytest.mark.asyncio
async def test_gate_rejection_recorded_once_then_suppressed_until_window_passes():
    world = World()
    world.place_error = TradeValidationError("Pre-market WAIT blocks automatic paper entries")
    now = at(10, 0)
    clock = {"now": now}
    preds = Predictions(prediction(now))
    e = engine(world, preds, now)
    e._clock = lambda: clock["now"]
    await e.check_once()
    clock["now"] = at(10, 5)
    preds.result = prediction(clock["now"])                  # each run sees a fresh quote
    note = await e.check_once()
    assert "not re-recorded" in note
    assert len(world.signals) == 1                           # the pending ELIGIBLE row was rolled back
    assert world.signals[0]["eligibility_status"] == PaperSignalEligibility.REJECTED_GATE
    assert world.signals[0]["rejection_reasons"] == ["Pre-market WAIT blocks automatic paper entries"]
    clock["now"] = at(10, 16)
    preds.result = prediction(clock["now"])
    await e.check_once()
    assert len(world.signals) == 2


@pytest.mark.asyncio
async def test_unexpected_order_error_is_recorded_not_lost():
    world = World()
    world.place_error = RuntimeError("db hiccup")
    now = at(10, 0)
    await engine(world, Predictions(prediction(now)), now).check_once()
    assert world.signals[0]["rejection_reasons"] == ["Execution error: RuntimeError: db hiccup"]


# ── square-off ───────────────────────────────────────────────────────────────

def tick(symbol, now, age=2, ltp=120.0):
    return Tick(symbol=symbol, ltp=ltp, prev_close=100, change=0, change_pct=0, timestamp=now, provider="ANGEL",
                fetched_at=now, exchange_timestamp=now - timedelta(seconds=age))


@pytest.mark.asyncio
async def test_square_off_closes_auto_positions_with_fresh_quotes_only():
    now, world = at(15, 15), World()
    fresh = SimpleNamespace(id=1, symbol=SYMBOL, status="OPEN", paper_signal_id=7)
    stale = SimpleNamespace(id=2, symbol="NIFTY17NOV2625000PE", status="OPEN", paper_signal_id=8)
    manual = SimpleNamespace(id=3, symbol="NIFTY17NOV2625100CE", status="OPEN", paper_signal_id=None)
    world.trades = [fresh, stale, manual]
    ticks = {SYMBOL: tick(SYMBOL, now), stale.symbol: tick(stale.symbol, now, age=120),
             manual.symbol: tick(manual.symbol, now)}
    preds = Predictions(prediction(now))
    note = await engine(world, preds, now, ticks=ticks).check_once()
    assert world.closed == [(1, 120.0, ExitReason.SQUARE_OFF)]
    assert stale.status == "OPEN" and manual.status == "OPEN"
    assert "deferred 1" in note
    assert preds.calls == []                                 # no new entries during square-off


def test_is_auto_trade_for_matches_underlying_prefix_only():
    t = SimpleNamespace(symbol="BANKNIFTY17NOV2652000CE", paper_signal_id=1)
    assert not is_auto_trade_for(t, OptionUnderlying.NIFTY)
    assert is_auto_trade_for(SimpleNamespace(symbol=SYMBOL, paper_signal_id=1), OptionUnderlying.NIFTY)
    assert not is_auto_trade_for(SimpleNamespace(symbol=SYMBOL, paper_signal_id=None), OptionUnderlying.NIFTY)
