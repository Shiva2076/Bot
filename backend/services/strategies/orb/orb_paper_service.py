from math import ceil
from typing import List, Optional

from config import settings
from repositories.strategy_signal_repository import StrategySignalRepository
from repositories.trade_repository import TradeRepository
from schemas.orb import OrbDecision, OrbEvaluateRequest, OrbExecuteResponse, OrbSignal
from schemas.personal_trade import TradeType
from schemas.trading import CandleInterval, MarketOrderRequest
from services.strategies.orb.orb_signal_engine import OrbSignalEngine
from services.trading.failover_market_data import FailoverMarketData
from services.trading.instrument_resolver import InstrumentResolver
from services.trading.order_service import OrderService
from services.personal.errors import TradeValidationError


class OrbPaperService:
    STRATEGY = "ORB_15M"

    def __init__(
        self,
        engine: OrbSignalEngine,
        market_data: FailoverMarketData,
        resolver: InstrumentResolver,
        order_service: OrderService,
        signals: StrategySignalRepository,
        trades: TradeRepository,
        interval: CandleInterval,
    ):
        self._engine = engine
        self._market_data = market_data
        self._resolver = resolver
        self._orders = order_service
        self._signals = signals
        self._trades = trades
        self._interval = interval

    async def evaluate(self, request: OrbEvaluateRequest) -> OrbSignal:
        instrument = await self._resolver.resolve(request.symbol)
        series = await self._market_data.get_candles(instrument.symbol, self._interval)
        return self._engine.evaluate(instrument.symbol, series.candles, settings.starting_capital)

    async def execute(self, request: OrbEvaluateRequest) -> OrbExecuteResponse:
        signal = await self.evaluate(request)
        if signal.decision not in {OrbDecision.LONG, OrbDecision.SHORT}:
            await self._signals.add(self.STRATEGY, signal, False, None, [])
            return OrbExecuteResponse(signal=signal, trade_id=None, executed=False, gate_reasons=[])

        existing = await self._signals.list_for_day(self.STRATEGY, signal.session_date)
        if any(s.symbol == signal.symbol and s.executed == "YES" for s in existing):
            signal.rejection_reason = "Already executed ORB for this symbol today"
            await self._signals.add(self.STRATEGY, signal, False, None, [signal.rejection_reason])
            return OrbExecuteResponse(signal=signal, trade_id=None, executed=False, gate_reasons=[signal.rejection_reason])

        instrument = await self._resolver.resolve(signal.symbol)
        lots = max(1, ceil(signal.quantity / instrument.lot_size))
        try:
            trade = await self._orders.place(
                MarketOrderRequest(
                    symbol=signal.symbol,
                    action=signal.action,
                    lots=lots,
                    stop_loss=signal.stop_loss,
                    target=signal.target,
                )
            )
        except TradeValidationError as e:
            reasons = str(e).split("; ")
            signal.rejection_reason = str(e)
            await self._signals.add(self.STRATEGY, signal, False, None, reasons)
            return OrbExecuteResponse(signal=signal, trade_id=None, executed=False, gate_reasons=reasons)

        await self._signals.add(self.STRATEGY, signal, True, trade.id, [])
        return OrbExecuteResponse(signal=signal, trade_id=trade.id, executed=True, gate_reasons=[])
