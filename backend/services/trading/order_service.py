from datetime import datetime
from typing import List, Optional

import pytz

from config import settings
from repositories.trade_repository import TradeRepository
from schemas.order_entry import (
    EntryAudit,
    EntryOrigin,
    OrderClassificationInput,
    PredictionGateSnapshot,
    SignalMatch,
)
from schemas.personal_trade import PersonalTradeView, TradeExitRequest, TradeType
from schemas.premarket import PremarketReport
from schemas.risk import PreTradeOrderContext
from schemas.trading import ExitReason, Instrument, MarketOrderRequest
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.errors import TradeValidationError
from services.personal.trade_mapper import PersonalTradeMapper
from services.risk.daily_risk_state import DailyRiskState, datetime_today
from services.risk.pre_trade_risk_gate import PreTradeRiskGate
from services.trading.failover_market_data import FailoverMarketData
from services.trading.instrument_resolver import InstrumentResolver
from services.trading.order_entry_gates import OrderEntryGates
from services.trading.order_validator import OrderValidator

STRATEGY_ORIGIN_NOTE = "Strategy entry; prediction match not evaluated"


class OrderService:
    def __init__(
        self,
        repository: TradeRepository,
        resolver: InstrumentResolver,
        market_data: FailoverMarketData,
        validator: OrderValidator,
        mapper: PersonalTradeMapper,
        risk_gate: PreTradeRiskGate,
        costs: PaperCostCalculator,
        daily_risk: DailyRiskState,
        gates: OrderEntryGates,
    ):
        self._repository = repository
        self._resolver = resolver
        self._market_data = market_data
        self._validator = validator
        self._mapper = mapper
        self._risk_gate = risk_gate
        self._costs = costs
        self._daily_risk = daily_risk
        self._gates = gates

    async def place(
        self,
        request: MarketOrderRequest,
        origin: EntryOrigin,
        paper_signal_id: Optional[int] = None,
    ) -> PersonalTradeView:
        self._gates.session.assert_entry_allowed()
        instrument = await self._resolver.resolve(request.symbol)
        tick = await self._market_data.get_tick(instrument.symbol)
        self._validator.validate_order(request, instrument, tick.ltp)
        report = await self._premarket_report()
        signal = await self._signal_match(instrument, request, origin)
        source = self._gates.classifier.classify(OrderClassificationInput(
            premarket_action=report.recommended_action,
            origin=origin,
            override_reason=request.override_reason,
            matches_actionable_signal=signal.matched,
        ))
        quantity = request.lots * instrument.lot_size
        await self._assert_risk_allows(request, quantity, tick, report)
        self._gates.session.assert_entry_allowed()

        if hasattr(self._repository, "acquire_order_lock"):
            await self._repository.acquire_order_lock()

        if paper_signal_id is not None:
            existing_trade = await self._repository.get_by_paper_signal_id(paper_signal_id)
            if existing_trade is not None:
                raise TradeValidationError(
                    f"Paper signal {paper_signal_id} has already executed trade {existing_trade.id}"
                )

        if await self._repository.count_open() >= settings.risk_max_open_positions:
            raise TradeValidationError(f"Maximum open positions reached ({settings.risk_max_open_positions})")

        trade_type = TradeType.PAPER if origin == EntryOrigin.AUTO_PAPER else TradeType.MANUAL
        audit = EntryAudit(
            order_source=source,
            override_reason=request.override_reason,
            premarket_action=report.recommended_action,
            prediction_gate=signal.snapshot,
        )
        trade = await self._repository.add(
            self._mapper.order_to_entity(
                request,
                instrument,
                tick.ltp,
                self._costs,
                audit,
                trade_type=trade_type,
                paper_signal_id=paper_signal_id,
            )
        )
        return self._mapper.to_view(trade, tick.ltp)

    async def exit(self, trade_id: int) -> PersonalTradeView:
        trade = await self._repository.get(trade_id)
        self._validator.validate_exit(trade)
        tick = await self._market_data.get_tick(trade.symbol)
        self._mapper.apply_exit(
            trade,
            TradeExitRequest(
                exit_price=tick.ltp,
                exit_time=datetime.now(pytz.utc),
                exit_reason=ExitReason.MANUAL.value,
            ),
            self._costs,
        )
        await self._trip_kill_switch_if_needed()
        return self._mapper.to_view(trade, None)

    async def list_open_positions(self, trade_type: Optional[TradeType] = TradeType.MANUAL) -> List[PersonalTradeView]:
        trades = await self._repository.list_open(trade_type)
        ticks = await self._market_data.get_ticks([t.symbol for t in trades])
        return [self._mapper.to_view(t, ticks[t.symbol].ltp if t.symbol in ticks else None) for t in trades]

    async def _premarket_report(self) -> PremarketReport:
        try:
            return await self._gates.premarket.analyze()
        except Exception as exc:
            raise TradeValidationError(f"Pre-market state unavailable; new entries are blocked ({type(exc).__name__})") from exc

    async def _signal_match(
        self, instrument: Instrument, request: MarketOrderRequest, origin: EntryOrigin
    ) -> SignalMatch:
        if origin == EntryOrigin.ORB_STRATEGY:
            return SignalMatch(matched=False, snapshot=PredictionGateSnapshot(available=False, note=STRATEGY_ORIGIN_NOTE))
        return await self._gates.signals.match(instrument, request)

    async def _assert_risk_allows(
        self, request: MarketOrderRequest, quantity: int, tick, report: PremarketReport
    ) -> None:
        open_count = await self._repository.count_open()
        realized_today = await self._repository.realized_pnl_on(datetime_today())
        if realized_today <= -settings.starting_capital * (settings.risk_daily_loss_limit_pct / 100.0):
            self._daily_risk.trip()
        cash = (
            settings.starting_capital
            - await self._repository.open_invested_total()
            + await self._repository.total_realized_pnl()
        )
        decision = self._risk_gate.evaluate(
            PreTradeOrderContext(
                symbol=request.symbol,
                action=request.action,
                quantity=quantity,
                entry_price=tick.ltp,
                stop_loss=request.stop_loss,
                tick_timestamp=tick.timestamp,
                tick_provider=tick.provider,
                exchange_timestamp=tick.exchange_timestamp,
                open_positions=open_count,
                starting_capital=settings.starting_capital,
                available_cash=cash,
                realized_pnl_today=realized_today,
                kill_switch_active=self._daily_risk.kill_switch_active,
                premarket_action=report.recommended_action,
                data_warnings=list(report.data_quality_warnings),
            )
        )
        if not decision.allowed:
            raise TradeValidationError("; ".join(decision.reasons))

    async def _trip_kill_switch_if_needed(self) -> None:
        realized_today = await self._repository.realized_pnl_on(datetime_today())
        limit = settings.starting_capital * (settings.risk_daily_loss_limit_pct / 100.0)
        if realized_today <= -limit:
            self._daily_risk.trip()
