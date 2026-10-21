from datetime import datetime
from typing import List, Optional

import pytz

from config import settings
from repositories.trade_repository import TradeRepository
from schemas.personal_trade import PersonalTradeView, TradeExitRequest, TradeType
from schemas.risk import PreTradeOrderContext
from schemas.trading import ExitReason, MarketOrderRequest
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.errors import TradeValidationError
from services.personal.trade_mapper import PersonalTradeMapper
from services.premarket.premarket_analyzer_service import PremarketAnalyzerService
from services.risk.daily_risk_state import DailyRiskState, datetime_today
from services.risk.pre_trade_risk_gate import PreTradeRiskGate
from services.trading.failover_market_data import FailoverMarketData
from services.trading.instrument_resolver import InstrumentResolver
from services.trading.order_validator import OrderValidator


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
        premarket: Optional[PremarketAnalyzerService],
        enforce_premarket_gate: bool,
    ):
        self._repository = repository
        self._resolver = resolver
        self._market_data = market_data
        self._validator = validator
        self._mapper = mapper
        self._risk_gate = risk_gate
        self._costs = costs
        self._daily_risk = daily_risk
        self._premarket = premarket
        self._enforce_premarket_gate = enforce_premarket_gate

    async def place(self, request: MarketOrderRequest) -> PersonalTradeView:
        instrument = await self._resolver.resolve(request.symbol)
        tick = await self._market_data.get_tick(instrument.symbol)
        self._validator.validate_order(request, instrument, tick.ltp)
        quantity = request.lots * instrument.lot_size
        await self._assert_risk_allows(request, quantity, tick)
        trade = await self._repository.add(
            self._mapper.order_to_entity(request, instrument, tick.ltp, self._costs)
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

    async def list_open_positions(self) -> List[PersonalTradeView]:
        trades = await self._repository.list_open(TradeType.MANUAL)
        ticks = await self._market_data.get_ticks([t.symbol for t in trades])
        return [self._mapper.to_view(t, ticks[t.symbol].ltp if t.symbol in ticks else None) for t in trades]

    async def _assert_risk_allows(self, request: MarketOrderRequest, quantity: int, tick) -> None:
        premarket_action = None
        warnings: List[str] = []
        if self._enforce_premarket_gate and self._premarket is not None:
            report = await self._premarket.analyze()
            premarket_action = report.recommended_action
            warnings = list(report.data_quality_warnings)
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
                open_positions=open_count,
                starting_capital=settings.starting_capital,
                available_cash=cash,
                realized_pnl_today=realized_today,
                kill_switch_active=self._daily_risk.kill_switch_active,
                premarket_action=premarket_action,
                data_warnings=warnings,
            )
        )
        if not decision.allowed:
            raise TradeValidationError("; ".join(decision.reasons))

    async def _trip_kill_switch_if_needed(self) -> None:
        realized_today = await self._repository.realized_pnl_on(datetime_today())
        limit = settings.starting_capital * (settings.risk_daily_loss_limit_pct / 100.0)
        if realized_today <= -limit:
            self._daily_risk.trip()
