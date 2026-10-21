import asyncio
from datetime import datetime
from typing import Dict, List

import pytz

from database import AsyncSessionLocal
from models.trade import Trade
from repositories.trade_repository import TradeRepository
from schemas.options import ParsedOptionSymbol
from schemas.personal_trade import TradeExitRequest, TradeType
from schemas.trading import ExitReason
from services.options.expiry_settlement_policy import ExpirySettlementPolicy
from services.options.option_chain_service import UNDERLYING_SPOT_SYMBOLS
from services.options.option_symbol_parser import OptionSymbolParser
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.failover_market_data import FailoverMarketData
from services.trading.stop_target_evaluator import StopTargetEvaluator


class RiskMonitor:
    def __init__(
        self,
        market_data: FailoverMarketData,
        evaluator: StopTargetEvaluator,
        parser: OptionSymbolParser,
        expiry_policy: ExpirySettlementPolicy,
        mapper: PersonalTradeMapper,
        costs: PaperCostCalculator,
        interval_seconds: float,
    ):
        self._market_data = market_data
        self._evaluator = evaluator
        self._parser = parser
        self._expiry_policy = expiry_policy
        self._mapper = mapper
        self._costs = costs
        self._interval_seconds = interval_seconds

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as e:
                print(f"Risk monitor error: {e}")
            await asyncio.sleep(self._interval_seconds)

    async def check_once(self) -> None:
        async with AsyncSessionLocal() as session:
            trades = await TradeRepository(session).list_open(TradeType.MANUAL)
            now = datetime.now(pytz.utc)
            expired: Dict[int, ParsedOptionSymbol] = {}
            for trade in trades:
                option = self._parser.parse(trade.symbol)
                if option and self._expiry_policy.is_expired(option, now):
                    expired[trade.id] = option
            await self._settle_expired([t for t in trades if t.id in expired], expired, now)
            await self._apply_stops([t for t in trades if t.id not in expired], now)
            await session.commit()

    async def _settle_expired(self, trades: List[Trade], options: Dict[int, ParsedOptionSymbol], now: datetime) -> None:
        spot_symbols = [UNDERLYING_SPOT_SYMBOLS[options[t.id].underlying] for t in trades]
        spots = await self._market_data.get_ticks(spot_symbols)
        for trade, spot_symbol in zip(trades, spot_symbols):
            if spot_symbol in spots:
                self._mapper.apply_exit(
                    trade,
                    TradeExitRequest(
                        exit_price=self._expiry_policy.settlement_price(options[trade.id], spots[spot_symbol].ltp),
                        exit_time=now,
                        exit_reason=ExitReason.EXPIRED.value,
                    ),
                    self._costs,
                )

    async def _apply_stops(self, trades: List[Trade], now: datetime) -> None:
        guarded = [t for t in trades if t.stop_loss is not None or t.target_1 is not None]
        ticks = await self._market_data.get_ticks([t.symbol for t in guarded])
        for trade in guarded:
            tick = ticks.get(trade.symbol)
            reason = self._evaluator.evaluate(trade, tick.ltp) if tick else None
            if reason:
                self._mapper.apply_exit(
                    trade,
                    TradeExitRequest(
                        exit_price=tick.ltp,
                        exit_time=now,
                        exit_reason=reason.value,
                    ),
                    self._costs,
                )
