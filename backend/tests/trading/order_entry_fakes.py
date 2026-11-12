from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytz

from models.trade import Trade
from schemas.costs import CostConfig
from schemas.options import OptionUnderlying
from schemas.personal_trade import TradeAction
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction
from schemas.trading import Instrument, InstrumentKind, MarketOrderRequest, Tick
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.options.option_symbol_parser import OptionSymbolParser
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper
from services.premarket.trading_calendar import SpecialSession, TradingCalendar
from services.risk.daily_risk_state import DailyRiskState
from services.risk.pre_trade_risk_gate import PreTradeRiskGate
from services.trading.actionable_signal_matcher import ActionableSignalMatcher, PredictionGateSnapshotMapper
from services.trading.entry_session_gate import EntrySessionGate
from services.trading.order_entry_gates import OrderEntryGates
from services.trading.order_service import OrderService
from services.trading.order_source_classifier import OrderSourceClassifier
from services.trading.order_validator import OrderValidator


class FakeContractResolver:
    def __init__(self) -> None:
        self._parser = OptionSymbolParser()

    async def resolve(self, symbol: str):
        return self._parser.parse(symbol)


IST = pytz.timezone("Asia/Kolkata")
STOCK = Instrument(symbol="RELIANCE.NS", name="Reliance", kind=InstrumentKind.STOCK, lot_size=1)
OPTION = Instrument(
    symbol="NIFTY27OCT2625000CE", name="NIFTY 25000 CE", kind=InstrumentKind.OPTION,
    lot_size=65, option_underlying=OptionUnderlying.NIFTY,
)
OTHER_OPTION_SYMBOL = "NIFTY27OCT2625100CE"
REGULAR_SESSION = IST.localize(datetime(2026, 10, 21, 11, 0))
PREMARKET_SESSION = IST.localize(datetime(2026, 10, 21, 9, 5))
AFTER_HOURS = IST.localize(datetime(2026, 10, 21, 15, 45))
WEEKEND = IST.localize(datetime(2026, 10, 24, 11, 0))
HOLIDAY = IST.localize(datetime(2026, 10, 20, 11, 0))
SPECIAL_DAY = IST.localize(datetime(2026, 11, 8, 18, 30))
HOLIDAYS = frozenset({date(2026, 10, 20)})
SPECIAL_SESSIONS = (SpecialSession(day=date(2026, 11, 8), start=time(18, 0), end=time(19, 0)),)


class ScriptedCalendar(TradingCalendar):
    """Returns each scripted moment in order, repeating the last one."""

    def __init__(self, *moments: datetime):
        super().__init__(HOLIDAYS, SPECIAL_SESSIONS)
        self._moments = list(moments)

    def now(self) -> datetime:
        if len(self._moments) > 1:
            return self._moments.pop(0)
        return self._moments[0]


class FakeRepo:
    def __init__(self):
        self.added: List[Trade] = []

    async def add(self, trade: Trade) -> Trade:
        trade.id = len(self.added) + 1
        self.added.append(trade)
        return trade

    async def get(self, trade_id: int) -> Trade:
        return self.added[trade_id - 1]

    async def count_open(self) -> int:
        return 0

    async def realized_pnl_on(self, day: date) -> float:
        return 0.0

    async def open_invested_total(self) -> float:
        return 0.0

    async def total_realized_pnl(self) -> float:
        return 0.0

    async def acquire_order_lock(self) -> None:
        pass

    async def list_open(self, trade_type=None, for_update: bool = False, skip_locked: bool = True) -> List[Trade]:
        trades = [t for t in self.added if t.status == "OPEN"]
        if trade_type is not None:
            expected = trade_type.value if hasattr(trade_type, "value") else str(trade_type)
            trades = [t for t in trades if getattr(t, "trade_type", None) == expected]
        return trades


    async def get_by_paper_signal_id(self, paper_signal_id: int) -> Optional[Trade]:
        for t in self.added:
            if getattr(t, "paper_signal_id", None) == paper_signal_id:
                return t
        return None

    async def has_open_for_symbol(self, symbol: str) -> bool:
        for t in self.added:
            if t.symbol == symbol and t.status == "OPEN":
                return True
        return False



class FakeResolver:
    def __init__(self, instrument: Instrument):
        self.instrument = instrument

    async def resolve(self, symbol: str) -> Instrument:
        return self.instrument


class FakeMarketData:
    def __init__(self, tick: Tick):
        self.tick = tick

    async def get_tick(self, symbol: str) -> Tick:
        return self.tick

    async def get_ticks(self, symbols: List[str]) -> Dict[str, Tick]:
        return {s: self.tick for s in symbols}


class FakePremarket:
    def __init__(self, action: Optional[RecommendedAction]):
        self.action = action
        self.calls = 0

    async def analyze(self):
        self.calls += 1
        if self.action is None:
            raise RuntimeError("premarket collectors down")
        return SimpleNamespace(recommended_action=self.action, data_quality_warnings=[])


class FakePredictions:
    def __init__(self, contract_symbol: Optional[str], gate_reason: GateReason = GateReason.NONE):
        self.contract_symbol = contract_symbol
        self.gate_reason = gate_reason
        self.calls = 0

    async def predict(self, underlying: OptionUnderlying, expiry: date):
        self.calls += 1
        if self.contract_symbol is None:
            raise RuntimeError("chain unavailable")
        actionable = self.gate_reason == GateReason.NONE
        return SimpleNamespace(
            direction=PredictionDirection.CALL if actionable else PredictionDirection.WAIT,
            gate_reason=self.gate_reason,
            data_freshness=DataFreshness.FRESH,
            session_status="REGULAR",
            contract=SimpleNamespace(quote=SimpleNamespace(symbol=self.contract_symbol)),
            generated_at=datetime.now(timezone.utc),
            log_id=None,
        )


def costs() -> PaperCostCalculator:
    return PaperCostCalculator(CostConfig(
        brokerage_pct=0.03, brokerage_flat=20, exchange_txn_pct=0.00345, sebi_pct=0.0001,
        stamp_duty_buy_pct=0.015, stt_sell_pct=0.025, gst_pct=18, slippage_bps=5,
    ))


def tick(symbol: str, ltp: float = 1000.0) -> Tick:
    now = datetime.now(timezone.utc)
    return Tick(
        symbol=symbol, ltp=ltp, prev_close=ltp, change=0.0, change_pct=0.0,
        timestamp=now, provider="ANGEL", fetched_at=now, exchange_timestamp=now,
    )


def gates(calendar: TradingCalendar, premarket: FakePremarket, predictions: FakePredictions) -> OrderEntryGates:
    return OrderEntryGates.model_construct(
        session=EntrySessionGate(calendar),
        premarket=premarket,
        signals=ActionableSignalMatcher(predictions, FakeContractResolver(), PredictionGateSnapshotMapper()),
        classifier=OrderSourceClassifier(),
    )


def order_service(
    repository, instrument: Instrument, entry_gates: OrderEntryGates, ltp: float = 1000.0
) -> OrderService:
    calculator = costs()
    return OrderService(
        repository=repository,
        resolver=FakeResolver(instrument),
        market_data=FakeMarketData(tick(instrument.symbol, ltp)),
        validator=OrderValidator(),
        mapper=PersonalTradeMapper(PnlCalculator()),
        risk_gate=PreTradeRiskGate(30, 1.0, 3.0, 5, calculator),
        costs=calculator,
        daily_risk=DailyRiskState(),
        gates=entry_gates,
    )


def stock_order(**extra) -> MarketOrderRequest:
    kwargs = {"symbol": STOCK.symbol, "action": TradeAction.BUY, "lots": 1, "stop_loss": 995.0}
    kwargs.update(extra)
    return MarketOrderRequest(**kwargs)


def option_order(**extra) -> MarketOrderRequest:
    kwargs = {"symbol": OPTION.symbol, "action": TradeAction.BUY, "lots": 1, "stop_loss": 95.0}
    kwargs.update(extra)
    return MarketOrderRequest(**kwargs)

