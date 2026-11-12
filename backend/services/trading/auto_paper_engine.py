"""
Automatic PAPER trading engine. Never sends broker orders.

Every `interval_seconds` during the regular session:
  * 09:20 <= time < 15:00 (configurable): ask for the current prediction per underlying. If it is
    an actionable CALL/PUT with a suggested contract, place a paper BUY through the normal
    OrderService with origin AUTO_PAPER, so every Phase 1 gate applies (session, exchange-time
    freshness, pre-market NO_TRADE/WAIT, signal match, risk limits). A spread/liquidity check
    (PaperFillModel) runs first.
  * At most one open auto position per underlying and `max_entries_per_day` entries per day.
  * time >= 15:15: square off open auto positions at a fresh quote (exit reason SQUARE_OFF).
    Exits never pass through the entry gates. Stop-loss/target/expiry exits stay with RiskMonitor.

Each actionable signal is recorded in paper_signals with its outcome. An identical rejection
(same contract, direction and reasons) is not re-recorded within `repeat_rejection_minutes`.
"""
import asyncio
import logging
import re
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional, Protocol, Tuple

import pytz

from schemas.options import OptionUnderlying
from schemas.order_entry import EntryOrigin
from schemas.paper_engine import (
    AutoPaperConfig,
    PaperExecutionStatus,
    PaperLifecycleEvent,
    PaperSignalCreate,
    PaperSignalEligibility,
    PaperSignalEventRecord,
)
from schemas.personal_trade import TradeAction, TradeExitRequest, TradeStatus
from schemas.prediction import GateReason, OptionPrediction, PredictionDirection
from schemas.trading import ExitReason, MarketOrderRequest, Tick
from services.personal.errors import TradeValidationError
from services.trading.exchange_timestamp_validator import ExchangeTimestampValidator
from services.trading.paper_fill_model import PaperFillModel

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")
REGULAR = "REGULAR"
ACTIONABLE = {PredictionDirection.CALL, PredictionDirection.PUT}


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def is_auto_trade_for(trade, underlying: OptionUnderlying) -> bool:
    return trade.paper_signal_id is not None and re.match(rf"^{underlying.value}\d", trade.symbol or "") is not None


class AutoPaperUnit(Protocol):
    """One database transaction's worth of operations the engine needs."""

    session: object  # passed to predict() so the prediction is logged

    async def open_auto_trades(self, for_update: bool = False) -> list: ...
    async def entries_on(self, underlying: OptionUnderlying, day: date) -> int: ...
    async def add_signal(self, data: PaperSignalCreate) -> int: ...
    async def update_signal(self, signal_id: int, **changes) -> None: ...
    async def place(self, request: MarketOrderRequest, signal_id: int): ...
    async def close_trade(self, trade, exit_price: float, at: datetime, reason: ExitReason) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class AutoPaperEngine:
    def __init__(
        self,
        config: AutoPaperConfig,
        calendar,
        predictions,
        expiries: Callable,                     # async (underlying) -> List[date]
        units: Callable[[], AbstractAsyncContextManager],
        fill_model: PaperFillModel,
        quotes: Callable,                       # async (symbols) -> Dict[str, Tick]
        scorer_version: str,
        max_quote_age_seconds: float = 30.0,
        max_future_skew_seconds: float = 5.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._config = config
        self._calendar = calendar
        self._predictions = predictions
        self._expiries = expiries
        self._units = units
        self._fill = fill_model
        self._quotes = quotes
        self._scorer_version = scorer_version
        self._max_age = max_quote_age_seconds
        self._max_skew = max_future_skew_seconds
        self._clock = clock
        self._entry_start = parse_hhmm(config.entry_start)
        self._last_entry = parse_hhmm(config.last_entry)
        self._square_off = parse_hhmm(config.square_off)
        self._last_rejection: Dict[OptionUnderlying, Tuple[str, datetime]] = {}
        self.last_run_at: Optional[datetime] = None
        self.last_note: Optional[str] = None

    @property
    def config(self) -> AutoPaperConfig:
        return self._config

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as exc:
                self.last_note = f"error: {type(exc).__name__}: {exc}"
                logger.error(f"Auto paper engine error: {exc}", exc_info=True)
            await asyncio.sleep(self._config.interval_seconds)

    async def check_once(self) -> str:
        now = self._clock()
        self.last_run_at = now
        note = await self._tick(now)
        self.last_note = note
        return note

    async def _tick(self, now: datetime) -> str:
        if not self._config.enabled:
            return "disabled"
        phase = self._calendar.session_phase(now)
        if phase != REGULAR:
            return f"idle: session phase {phase}"
        clock = now.astimezone(IST).time()
        if clock >= self._square_off:
            return await self._square_off_open(now)
        if clock < self._entry_start or clock >= self._last_entry:
            return f"no new entries at {clock:%H:%M} (window {self._entry_start:%H:%M}-{self._last_entry:%H:%M})"
        notes = [await self._consider(u, now) for u in self._config.underlyings]
        return "; ".join(notes)

    # ── entries ───────────────────────────────────────────────────────────────

    async def _consider(self, underlying: OptionUnderlying, now: datetime) -> str:
        expiries = await self._expiries(underlying)
        if not expiries:
            return f"{underlying.value}: no expiry available"
        async with self._units() as unit:
            prediction: OptionPrediction = await self._predictions.predict(underlying, expiries[0], session=unit.session)
            await unit.commit()
        if (
            prediction.direction not in ACTIONABLE
            or prediction.gate_reason != GateReason.NONE
            or prediction.contract is None
        ):
            return f"{underlying.value}: {prediction.direction.value} ({prediction.gate_reason.value}), no entry"

        async with self._units() as unit:
            if any(is_auto_trade_for(t, underlying) for t in await unit.open_auto_trades()):
                return f"{underlying.value}: auto position already open"
            if await unit.entries_on(underlying, now.astimezone(IST).date()) >= self._config.max_entries_per_day:
                return f"{underlying.value}: daily auto entry limit {self._config.max_entries_per_day} reached"

            contract = prediction.contract
            quantity = self._config.lots * prediction.lot_size
            fill = self._fill.evaluate_buy_fill(contract.quote, quantity, now)
            if not fill.success:
                return await self._record_rejection(
                    unit, underlying, prediction, now, PaperSignalEligibility.REJECTED_FILL, fill.rejection_reasons
                )

            signal_id = await unit.add_signal(self._signal(prediction, now, PaperSignalEligibility.ELIGIBLE,
                                                           PaperExecutionStatus.PENDING, []))
            request = MarketOrderRequest(
                symbol=contract.quote.symbol,
                action=TradeAction.BUY,
                lots=self._config.lots,
                stop_loss=contract.levels.stop_loss,
                target=contract.levels.target,
            )
            try:
                trade = await unit.place(request, signal_id)
            except Exception as exc:
                # Gate/risk rejections arrive as TradeValidationError; anything else is recorded too.
                await unit.rollback()
                reasons = (
                    str(exc).split("; ") if isinstance(exc, TradeValidationError)
                    else [f"Execution error: {type(exc).__name__}: {exc}"]
                )
                return await self._record_rejection(
                    unit, underlying, prediction, now, PaperSignalEligibility.REJECTED_GATE, reasons
                )
            await unit.update_signal(
                signal_id,
                execution_status=PaperExecutionStatus.EXECUTED,
                trade_id=trade.id,
                event=PaperSignalEventRecord(
                    timestamp=now, event_type=PaperLifecycleEvent.PAPER_ENTRY_FILLED,
                    details={"trade_id": trade.id, "entry_price": trade.entry_price, "quantity": trade.quantity},
                ),
            )
            await unit.commit()
            self._last_rejection.pop(underlying, None)
            return f"{underlying.value}: paper BUY {contract.quote.symbol} x{trade.quantity} (trade {trade.id})"

    async def _record_rejection(
        self, unit, underlying: OptionUnderlying, prediction: OptionPrediction, now: datetime,
        eligibility: PaperSignalEligibility, reasons: List[str],
    ) -> str:
        key = f"{prediction.contract.quote.symbol}|{prediction.direction.value}|{eligibility.value}|{'|'.join(reasons)}"
        last = self._last_rejection.get(underlying)
        window = timedelta(minutes=self._config.repeat_rejection_minutes)
        summary = f"{underlying.value}: {eligibility.value}: {'; '.join(reasons)}"
        if last is not None and last[0] == key and now - last[1] < window:
            return summary + " (repeat, not re-recorded)"
        await unit.add_signal(self._signal(prediction, now, eligibility, PaperExecutionStatus.SKIPPED, reasons))
        await unit.commit()
        self._last_rejection[underlying] = (key, now)
        return summary

    def _signal(
        self, p: OptionPrediction, now: datetime, eligibility: PaperSignalEligibility,
        execution: PaperExecutionStatus, reasons: List[str],
    ) -> PaperSignalCreate:
        c = p.contract
        event = PaperLifecycleEvent.SIGNAL_GENERATED if not reasons else PaperLifecycleEvent.SIGNAL_REJECTED
        return PaperSignalCreate(
            signal_uuid=str(uuid.uuid4()),
            session_date=now.astimezone(IST).date(),
            generated_at=p.generated_at,
            underlying=p.underlying,
            strategy="AUTO_OPTION_PREDICTION",
            direction=p.direction,
            score=p.score,
            raw_score=p.raw_score,
            signal_score=p.signal_score,
            confidence=p.confidence,
            scorer_version=self._scorer_version,
            spot_level=p.spot,
            contract_symbol=c.quote.symbol,
            contract_strike=c.strike,
            contract_expiry=p.expiry,
            contract_option_type=c.option_type,
            entry_premium=c.levels.entry,
            stop_loss=c.levels.stop_loss,
            target=c.levels.target,
            quote_ltp=c.quote.ltp,
            quote_bid=c.quote.bid,
            quote_ask=c.quote.ask,
            quote_volume=c.quote.volume,
            quote_oi=c.quote.open_interest,
            quote_exchange_timestamp=c.quote.exchange_timestamp,
            quote_provider="ANGEL",
            quote_freshness=p.data_freshness,
            gate_reason=p.gate_reason,
            premarket_action=p.premarket_action,
            premarket_wait_trigger=p.premarket_wait_trigger,
            eligibility_status=eligibility,
            execution_status=execution,
            rejection_reasons=reasons,
            prediction_snapshot={"log_id": p.log_id, "score": p.score, "signal_score": p.signal_score},
            events=[PaperSignalEventRecord(timestamp=now, event_type=event,
                                           details={"reasons": reasons} if reasons else None)],
        )

    # ── square-off ────────────────────────────────────────────────────────────

    async def _square_off_open(self, now: datetime) -> str:
        async with self._units() as unit:
            trades = [t for t in await unit.open_auto_trades(for_update=True) if t.status == TradeStatus.OPEN.value]
            if not trades:
                return "square-off: no open auto positions"
            ticks = await self._quotes([t.symbol for t in trades])
            closed, deferred = [], []
            for trade in trades:
                tick = ticks.get(trade.symbol)
                if tick is None or tick.ltp <= 0 or not self._fresh(tick, now):
                    deferred.append(trade.symbol)
                    continue
                await unit.close_trade(trade, tick.ltp, now, ExitReason.SQUARE_OFF)
                closed.append(trade.symbol)
            await unit.commit()
        note = f"square-off: closed {len(closed)}"
        if deferred:
            note += f", deferred {len(deferred)} without a fresh quote ({', '.join(deferred)}); retrying"
        return note

    def _fresh(self, tick: Tick, now: datetime) -> bool:
        ts = tick.exchange_timestamp
        if ts is None or not ExchangeTimestampValidator.is_plausible(ts):
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds()
        return -self._max_skew <= age <= self._max_age
