from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest
import pytz

from schemas.angel import AngelQuote
from schemas.trading import Candle, CandleInterval, Tick
from scripts.diagnose_tick_timestamps import TickTimestampDiagnostic
from services.brokers.angel.quote_mapper import AngelQuoteMapper
from services.trading.errors import MarketDataUnavailableError
from services.trading.failover_market_data import FailoverMarketData
from services.trading.market_data_provider import MarketDataProvider

IST = pytz.timezone("Asia/Kolkata")
FETCHED = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)


def _quote(trade: Optional[str], feed: Optional[str]) -> AngelQuote:
    return AngelQuote(
        exchange="NSE", tradingSymbol="RELIANCE-EQ", symbolToken="2885",
        ltp=1000.0, close=990.0, netChange=10.0, percentChange=1.0,
        exchTradeTime=trade, exchFeedTime=feed,
    )


def test_angel_trade_time_preferred_and_localized_to_ist():
    tick = AngelQuoteMapper().to_tick("RELIANCE.NS", _quote("21-Oct-2026 10:29:50", "21-Oct-2026 10:29:55"), "ANGEL", FETCHED)
    assert tick.exchange_timestamp == IST.localize(datetime(2026, 10, 21, 10, 29, 50))
    assert tick.exchange_timestamp.utcoffset() == timedelta(hours=5, minutes=30)
    assert tick.timestamp == tick.exchange_timestamp
    assert tick.fetched_at == FETCHED


def test_angel_epoch_trade_time_discarded_feed_time_used():
    tick = AngelQuoteMapper().to_tick("^NSEI", _quote("01-Jan-1970 05:30:00", "21-Oct-2026 16:08:11"), "ANGEL", FETCHED)
    assert tick.exchange_timestamp == IST.localize(datetime(2026, 10, 21, 16, 8, 11))


@pytest.mark.parametrize("trade,feed", [
    (None, None),
    ("", "  "),
    ("0", "0.0"),
    ("garbage", "21/10/2026 10:00"),
    ("01-Jan-1970 05:30:00", "01-Jan-1970 05:30:00"),
])
def test_angel_unusable_exchange_fields_fall_back_to_fetch_time_on_tick_timestamp(trade, feed):
    tick = AngelQuoteMapper().to_tick("RELIANCE.NS", _quote(trade, feed), "ANGEL", FETCHED)
    assert tick.exchange_timestamp is None
    assert tick.timestamp == FETCHED


class _Provider(MarketDataProvider):
    def __init__(self, name: str, ticks: Dict[str, Tick], fail: bool = False):
        self._name = name
        self._ticks = ticks
        self._fail = fail

    @property
    def name(self) -> str:
        return self._name

    async def get_tick(self, symbol: str) -> Optional[Tick]:
        return (await self.get_ticks([symbol])).get(symbol)

    async def get_ticks(self, symbols: List[str]) -> Dict[str, Tick]:
        if self._fail:
            raise RuntimeError("provider down")
        return {s: self._ticks[s] for s in symbols if s in self._ticks}

    async def get_candles(self, symbol: str, interval: CandleInterval) -> List[Candle]:
        return []


def _tick(provider: str, exchange: Optional[datetime]) -> Tick:
    return Tick(
        symbol="RELIANCE.NS", ltp=1000.0, prev_close=990.0, change=10.0, change_pct=1.0,
        timestamp=exchange or FETCHED, provider=provider, fetched_at=FETCHED, exchange_timestamp=exchange,
    )


@pytest.mark.asyncio
async def test_failover_prefers_angel_exchange_tick():
    exchange = FETCHED - timedelta(seconds=3)
    failover = FailoverMarketData([
        _Provider("ANGEL", {"RELIANCE.NS": _tick("ANGEL", exchange)}),
        _Provider("YAHOO", {"RELIANCE.NS": _tick("YAHOO", None)}),
    ])
    tick = await failover.get_tick("RELIANCE.NS")
    assert tick.provider == "ANGEL"
    assert tick.exchange_timestamp == exchange


@pytest.mark.asyncio
async def test_failover_to_yahoo_when_angel_fails():
    """Yahoo may fill the quote gap; order path still rejects missing exchange timestamps."""
    failover = FailoverMarketData([
        _Provider("ANGEL", {}, fail=True),
        _Provider("YAHOO", {"RELIANCE.NS": _tick("YAHOO", None)}),
    ])
    tick = await failover.get_tick("RELIANCE.NS")
    assert tick.provider == "YAHOO"
    assert tick.exchange_timestamp is None
    assert tick.timestamp == tick.fetched_at


@pytest.mark.asyncio
async def test_failover_upgrades_to_exchange_verified_from_later_provider():
    exchange = FETCHED - timedelta(seconds=2)
    failover = FailoverMarketData([
        _Provider("YAHOO", {"RELIANCE.NS": _tick("YAHOO", None)}),
        _Provider("ANGEL", {"RELIANCE.NS": _tick("ANGEL", exchange)}),
    ])
    tick = await failover.get_tick("RELIANCE.NS")
    assert tick.provider == "ANGEL"
    assert tick.exchange_timestamp == exchange


@pytest.mark.asyncio
async def test_preferred_tick_skips_yahoo_gap_fill():
    failover = FailoverMarketData([
        _Provider("ANGEL", {}, fail=True),
        _Provider("YAHOO", {"RELIANCE.NS": _tick("YAHOO", None)}),
    ])
    with pytest.raises(MarketDataUnavailableError, match="ANGEL"):
        await failover.get_preferred_tick("RELIANCE.NS")


@pytest.mark.asyncio
async def test_preferred_tick_retries_once_before_failing():
    class Flaky(_Provider):
        def __init__(self) -> None:
            super().__init__("ANGEL", {})
            self.calls = 0

        async def get_ticks(self, symbols):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient")
            exchange = FETCHED - timedelta(seconds=1)
            return {s: _tick("ANGEL", exchange) for s in symbols}

    flaky = Flaky()
    failover = FailoverMarketData([flaky, _Provider("YAHOO", {"RELIANCE.NS": _tick("YAHOO", None)})])
    tick = await failover.get_preferred_tick("RELIANCE.NS")
    assert flaky.calls == 2
    assert tick.provider == "ANGEL"
    assert tick.exchange_timestamp is not None


def test_diagnostic_labels_timestamp_basis():
    exchange = FETCHED - timedelta(seconds=5)
    assert TickTimestampDiagnostic._from_tick("X", "ANGEL", _tick("ANGEL", exchange)).tick_timestamp_basis == "EXCHANGE"
    assert TickTimestampDiagnostic._from_tick("X", "YAHOO", _tick("YAHOO", None)).tick_timestamp_basis == "FETCH"


def test_yahoo_tick_rejected_by_pre_trade_risk_gate():
    from schemas.costs import CostConfig
    from schemas.personal_trade import TradeAction
    from schemas.risk import PreTradeOrderContext
    from services.costs.paper_cost_calculator import PaperCostCalculator
    from services.risk.pre_trade_risk_gate import PreTradeRiskGate

    gate = PreTradeRiskGate(
        max_data_age_seconds=30.0,
        max_risk_per_trade_pct=1.0,
        daily_loss_limit_pct=3.0,
        max_open_positions=5,
        cost_calculator=PaperCostCalculator(CostConfig(
            brokerage_pct=0.03, brokerage_flat=20.0, exchange_txn_pct=0.00345,
            sebi_pct=0.0001, stamp_duty_buy_pct=0.015, stt_sell_pct=0.025,
            gst_pct=18.0, slippage_bps=5.0,
        )),
    )
    yahoo_tick = _tick("YAHOO", None)
    context = PreTradeOrderContext(
        symbol=yahoo_tick.symbol,
        action=TradeAction.BUY,
        quantity=1,
        entry_price=yahoo_tick.ltp,
        stop_loss=990.0,
        tick_timestamp=yahoo_tick.timestamp,
        tick_provider=yahoo_tick.provider,
        exchange_timestamp=yahoo_tick.exchange_timestamp,
        open_positions=0,
        starting_capital=1_000_000.0,
        available_cash=1_000_000.0,
        realized_pnl_today=0.0,
        kill_switch_active=False,
    )
    decision = gate.evaluate(context)
    assert decision.allowed is False
    assert any("Missing verified exchange timestamp" in r for r in decision.reasons)

