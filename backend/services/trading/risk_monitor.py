import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytz

from database import AsyncSessionLocal
from models.trade import Trade
from repositories.trade_repository import TradeRepository
from schemas.options import ParsedOptionSymbol
from schemas.personal_trade import TradeExitRequest, TradeStatus, TradeType
from schemas.trading import ExitReason, Tick
from services.options.expiry_settlement_policy import ExpirySettlementPolicy
from services.options.option_chain_service import UNDERLYING_SPOT_SYMBOLS
from services.options.option_contract_resolver import OptionContractResolver
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.trading.exchange_timestamp_validator import ExchangeTimestampValidator
from services.trading.failover_market_data import FailoverMarketData
from services.trading.stop_target_evaluator import StopTargetEvaluator

logger = logging.getLogger(__name__)


class RiskMonitor:
    def __init__(
        self,
        market_data: FailoverMarketData,
        evaluator: StopTargetEvaluator,
        contracts: OptionContractResolver,
        expiry_policy: ExpirySettlementPolicy,
        mapper: PersonalTradeMapper,
        costs: PaperCostCalculator,
        interval_seconds: float,
        session_factory=None,
        max_data_age_seconds: float = 30.0,
    ):
        self._market_data = market_data
        self._evaluator = evaluator
        self._contracts = contracts
        self._expiry_policy = expiry_policy
        self._mapper = mapper
        self._costs = costs
        self._interval_seconds = interval_seconds
        self._session_factory = session_factory or AsyncSessionLocal
        self._max_data_age_seconds = max_data_age_seconds
        self._unresolved_exposures: Dict[int, Dict[str, Any]] = {}

    @property
    def unresolved_exposures(self) -> Dict[int, Dict[str, Any]]:
        return dict(self._unresolved_exposures)

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except Exception as e:
                logger.error(f"Risk monitor error: {e}", exc_info=True)
            await asyncio.sleep(self._interval_seconds)

    async def check_once(self) -> None:
        async with self._session_factory() as session:
            trades = await TradeRepository(session).list_open(for_update=True)
            for t in trades:
                if isinstance(t.tags, dict) and "unresolved_exposure" in t.tags:
                    self._unresolved_exposures[t.id] = t.tags["unresolved_exposure"]

            now = datetime.now(pytz.utc)
            expired: Dict[int, ParsedOptionSymbol] = {}
            for trade in trades:
                option = await self._contracts.resolve(trade.symbol)
                if option and self._expiry_policy.is_expired(option, now):
                    expired[trade.id] = option
            await self._settle_expired([t for t in trades if t.id in expired], expired, now)
            await self._apply_stops([t for t in trades if t.id not in expired], now)
            await session.commit()

    def _is_tick_fresh(self, tick: Tick, now: Optional[datetime] = None) -> bool:
        ex_ts = tick.exchange_timestamp
        if ex_ts is None:
            return False
        if not ExchangeTimestampValidator.is_plausible(ex_ts):
            return False
        if ex_ts.tzinfo is None:
            ex_ts = ex_ts.replace(tzinfo=timezone.utc)
        eval_time = now if now is not None else datetime.now(timezone.utc)
        if eval_time.tzinfo is None:
            eval_time = eval_time.replace(tzinfo=timezone.utc)
        age = (eval_time.astimezone(timezone.utc) - ex_ts.astimezone(timezone.utc)).total_seconds()
        wall_now = datetime.now(timezone.utc)
        wall_age = (wall_now - ex_ts.astimezone(timezone.utc)).total_seconds()
        if (-5.0 <= age <= self._max_data_age_seconds) or (-5.0 <= wall_age <= self._max_data_age_seconds):
            return True
        return False

    def _record_unresolved_exposure(self, trade: Trade, reason: str, now: datetime) -> None:
        payload = {
            "trade_id": trade.id,
            "symbol": trade.symbol,
            "reason": reason,
            "timestamp": now.isoformat() if hasattr(now, "isoformat") else str(now),
            "trade_type": trade.trade_type,
        }
        self._unresolved_exposures[trade.id] = payload
        tags = dict(trade.tags or {})
        tags["unresolved_exposure"] = payload
        trade.tags = tags
        logger.warning(f"Exit deferred for trade {trade.id} ({trade.symbol}): {reason}")

    def _clear_unresolved_exposure(self, trade: Trade) -> None:
        self._unresolved_exposures.pop(trade.id, None)
        if isinstance(trade.tags, dict) and "unresolved_exposure" in trade.tags:
            tags = dict(trade.tags)
            tags.pop("unresolved_exposure", None)
            trade.tags = tags

    async def _settle_expired(self, trades: List[Trade], options: Dict[int, ParsedOptionSymbol], now: datetime) -> None:
        spot_symbols = [UNDERLYING_SPOT_SYMBOLS.get(options[t.id].underlying) for t in trades]
        valid_symbols = [s for s in spot_symbols if s]
        spots = await self._market_data.get_ticks(valid_symbols)
        for trade, spot_symbol in zip(trades, spot_symbols):
            if trade.status != TradeStatus.OPEN.value:
                continue
            if not spot_symbol:
                self._record_unresolved_exposure(
                    trade, f"No spot mapping for underlying {options[trade.id].underlying}", now
                )
                continue
            spot_tick = spots.get(spot_symbol)
            if spot_tick is None or spot_tick.ltp <= 0:
                self._record_unresolved_exposure(
                    trade, f"Underlying spot quote {spot_symbol} unavailable for settlement", now
                )
                continue

            if not self._is_tick_fresh(spot_tick, now):
                self._record_unresolved_exposure(
                    trade, f"Underlying spot quote {spot_symbol} stale for settlement (ts: {spot_tick.exchange_timestamp})", now
                )
                continue

            self._clear_unresolved_exposure(trade)
            settlement_price = self._expiry_policy.settlement_price(options[trade.id], spot_tick.ltp)
            self._mapper.apply_exit(
                trade,
                TradeExitRequest(
                    exit_price=settlement_price,
                    exit_time=now,
                    exit_reason=ExitReason.EXPIRED.value,
                ),
                self._costs,
            )

    async def _apply_stops(self, trades: List[Trade], now: datetime) -> None:
        guarded = [t for t in trades if t.stop_loss is not None or t.target_1 is not None]
        ticks = await self._market_data.get_ticks([t.symbol for t in guarded])
        for trade in guarded:
            if trade.status != TradeStatus.OPEN.value:
                continue
            tick = ticks.get(trade.symbol)
            if tick is None or tick.ltp <= 0:
                self._record_unresolved_exposure(trade, "Quote unavailable", now)
                continue

            if not self._is_tick_fresh(tick, now):
                self._record_unresolved_exposure(trade, f"Quote stale (exchange_ts: {tick.exchange_timestamp})", now)
                continue

            self._clear_unresolved_exposure(trade)
            reason = self._evaluator.evaluate(trade, tick.ltp)
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


