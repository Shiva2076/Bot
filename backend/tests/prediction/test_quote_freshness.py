from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pytest
import pytz

from schemas.angel import AngelQuote
from schemas.options import OptionQuote, OptionUnderlying
from schemas.prediction import DataFreshness, FreshnessBasis, GateReason, PredictionDirection
from schemas.trading import Tick
from services.brokers.angel.quote_mapper import AngelQuoteMapper
from services.prediction.prediction_market_gate import (
    DEFAULT_MAX_FUTURE_SKEW_SECONDS,
    PredictionMarketGate,
)
from services.premarket.trading_calendar import TradingCalendar
from tests.prediction.test_prediction_gate_e2e import _chain, _service

IST = pytz.timezone("Asia/Kolkata")


def _gate(
    max_age: float = 30.0,
    max_future_skew: float = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
) -> PredictionMarketGate:
    return PredictionMarketGate(TradingCalendar(set()), max_age, max_future_skew)


def _regular_now() -> datetime:
    return IST.localize(datetime(2026, 10, 21, 10, 30)).astimezone(timezone.utc)


def _spot(
    exchange: datetime,
    fetched: datetime,
    symbol: str = "^NSEI",
) -> Tick:
    return Tick(
        symbol=symbol,
        ltp=1,
        prev_close=1,
        change=0,
        change_pct=0,
        timestamp=exchange,
        provider="ANGEL",
        fetched_at=fetched,
        exchange_timestamp=exchange,
    )


def _option(
    exchange: Optional[datetime],
    fetched: datetime,
    symbol: str = "NIFTY21OCT2625000CE",
) -> OptionQuote:
    return OptionQuote(
        symbol=symbol,
        display_name=symbol,
        ltp=100,
        change=0,
        change_pct=0,
        open_interest=1,
        volume=1,
        bid=99,
        ask=101,
        fetched_at=fetched,
        exchange_timestamp=exchange,
    )


def test_angel_parses_exchange_trade_time_not_fetch_time():
    fetched = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)
    quote = AngelQuote(
        exchange="NSE",
        tradingSymbol="Nifty 50",
        symbolToken="99926000",
        ltp=25000.0,
        close=24900.0,
        netChange=100.0,
        percentChange=0.4,
        exchTradeTime="21-Oct-2026 10:29:50",
        exchFeedTime="21-Oct-2026 10:29:55",
    )
    tick = AngelQuoteMapper().to_tick("^NSEI", quote, "ANGEL", fetched)
    assert tick.fetched_at == fetched
    assert tick.exchange_timestamp is not None
    assert tick.exchange_timestamp.astimezone(IST).strftime("%H:%M:%S") == "10:29:50"
    assert tick.timestamp == tick.exchange_timestamp


def test_angel_epoch_trade_time_falls_through_to_feed_time():
    """Index quotes often send exchTradeTime as 01-Jan-1970; use feed time instead."""
    fetched = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)
    quote = AngelQuote(
        exchange="NSE",
        tradingSymbol="Nifty 50",
        symbolToken="99926000",
        ltp=23074.9,
        close=22888.95,
        netChange=185.95,
        percentChange=0.81,
        exchTradeTime="01-Jan-1970 05:30:00",
        exchFeedTime="21-Oct-2026 09:25:10",
    )
    tick = AngelQuoteMapper().to_tick("^NSEI", quote, "ANGEL", fetched)
    assert tick.exchange_timestamp is not None
    assert tick.exchange_timestamp.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") == "2026-10-21 09:25:10"
    now = IST.localize(datetime(2026, 10, 21, 9, 25, 20)).astimezone(timezone.utc)
    result = _gate().evaluate(now, [tick])
    assert result.gate_reason == GateReason.NONE
    assert result.data_freshness == DataFreshness.FRESH
    assert result.quotes[0].verified is True
    assert result.quotes[0].basis == FreshnessBasis.EXCHANGE


def test_epoch_only_exchange_time_is_unknown_not_stale():
    now = _regular_now()
    epoch = datetime(1970, 1, 1, 5, 30, tzinfo=IST)
    tick = Tick(
        symbol="^NSEI", ltp=23074.9, prev_close=22888.95, change=0, change_pct=0,
        timestamp=epoch, provider="ANGEL", fetched_at=now, exchange_timestamp=epoch,
    )
    result = _gate().evaluate(now, [tick])
    assert result.gate_reason == GateReason.UNKNOWN_FRESHNESS
    assert result.data_freshness == DataFreshness.UNKNOWN
    assert result.quotes[0].verified is False
    assert result.quotes[0].basis == FreshnessBasis.FETCH
    assert result.blocks_action


def test_missing_exchange_time_is_not_labelled_fresh():
    fetched = _regular_now()
    quote = AngelQuote(
        exchange="NSE",
        tradingSymbol="Nifty 50",
        symbolToken="99926000",
        ltp=25000.0,
        close=24900.0,
        netChange=0.0,
        percentChange=0.0,
    )
    tick = AngelQuoteMapper().to_tick("^NSEI", quote, "ANGEL", fetched)
    assert tick.exchange_timestamp is None
    result = _gate().evaluate(fetched, [tick])
    assert result.gate_reason == GateReason.UNKNOWN_FRESHNESS
    assert result.data_freshness == DataFreshness.UNKNOWN
    assert result.quotes[0].basis == FreshnessBasis.FETCH
    assert result.quotes[0].verified is False
    assert result.blocks_action


def test_verified_fresh_and_stale_exchange_timestamps():
    now = _regular_now()
    fresh_exchange = now - timedelta(seconds=10)
    stale_exchange = now - timedelta(seconds=45)
    fresh = _spot(fresh_exchange, now)
    stale = _spot(stale_exchange, now)
    assert _gate().evaluate(now, [fresh]).gate_reason == GateReason.NONE
    assert _gate().evaluate(now, [fresh]).data_freshness == DataFreshness.FRESH
    assert _gate().evaluate(now, [fresh]).quotes[0].verified is True
    assert _gate().evaluate(now, [stale]).gate_reason == GateReason.STALE_DATA
    assert _gate().evaluate(now, [stale]).blocks_action


def test_recent_fetch_without_exchange_time_still_blocks():
    now = _regular_now()
    tick = Tick(
        symbol="^NSEI", ltp=1, prev_close=1, change=0, change_pct=0,
        timestamp=now, provider="YAHOO", fetched_at=now, exchange_timestamp=None,
    )
    result = _gate().evaluate(now, [tick])
    assert result.gate_reason == GateReason.UNKNOWN_FRESHNESS
    assert result.blocks_action


def test_option_quote_unknown_blocks_even_if_spot_fresh():
    now = _regular_now()
    spot = _spot(now - timedelta(seconds=5), now)
    option = _option(None, now)
    result = _gate().evaluate(now, [spot], [option])
    assert result.gate_reason == GateReason.UNKNOWN_FRESHNESS
    assert result.blocks_action


def test_quote_arriving_after_request_start_needs_evaluation_boundary():
    """Regression: exchange after request_start is FRESH only when evaluated later."""
    request_start = _regular_now()
    exchange = request_start + timedelta(seconds=20)
    fetched = request_start + timedelta(seconds=20)
    evaluated_at = request_start + timedelta(seconds=21)
    tick = _spot(exchange, fetched)

    stale_clock = _gate().evaluate(request_start, [tick])
    assert stale_clock.gate_reason == GateReason.UNKNOWN_FRESHNESS
    assert stale_clock.quotes[0].age_seconds == pytest.approx(-20.0)

    correct = _gate().evaluate(evaluated_at, [tick])
    assert correct.gate_reason == GateReason.NONE
    assert correct.data_freshness == DataFreshness.FRESH
    assert correct.quotes[0].verified is True
    assert correct.quotes[0].basis == FreshnessBasis.EXCHANGE
    assert correct.quotes[0].age_seconds == pytest.approx(1.0)


def test_option_and_spot_share_evaluation_boundary():
    request_start = _regular_now()
    exchange = request_start + timedelta(seconds=15)
    evaluated_at = request_start + timedelta(seconds=16)
    spot = _spot(exchange, exchange)
    option = _option(exchange, exchange)

    assert _gate().evaluate(request_start, [spot], [option]).gate_reason == GateReason.UNKNOWN_FRESHNESS
    result = _gate().evaluate(evaluated_at, [spot], [option])
    assert result.gate_reason == GateReason.NONE
    assert result.data_freshness == DataFreshness.FRESH
    assert all(q.verified and q.basis == FreshnessBasis.EXCHANGE for q in result.quotes)


def test_small_future_skew_is_fresh_with_zero_age():
    now = _regular_now()
    exchange = now + timedelta(seconds=DEFAULT_MAX_FUTURE_SKEW_SECONDS)
    result = _gate().evaluate(now, [_spot(exchange, now)])
    assert result.gate_reason == GateReason.NONE
    assert result.data_freshness == DataFreshness.FRESH
    assert result.quotes[0].verified is True
    assert result.quotes[0].basis == FreshnessBasis.EXCHANGE
    assert result.quotes[0].age_seconds == 0.0


def test_material_future_exchange_timestamp_is_never_fresh():
    now = _regular_now()
    exchange = now + timedelta(seconds=DEFAULT_MAX_FUTURE_SKEW_SECONDS + 1)
    result = _gate().evaluate(now, [_spot(exchange, now)])
    assert result.gate_reason == GateReason.UNKNOWN_FRESHNESS
    assert result.data_freshness == DataFreshness.UNKNOWN
    assert result.quotes[0].verified is False
    assert result.quotes[0].basis == FreshnessBasis.UNKNOWN
    assert result.quotes[0].age_seconds < 0
    assert result.blocks_action


def test_ist_exchange_timestamp_compared_in_utc():
    """IST-localized exchange times must compare correctly against UTC evaluation clock."""
    exchange_ist = IST.localize(datetime(2026, 10, 21, 10, 29, 50))
    evaluated_utc = IST.localize(datetime(2026, 10, 21, 10, 30, 0)).astimezone(timezone.utc)
    tick = _spot(exchange_ist, evaluated_utc)
    result = _gate().evaluate(evaluated_utc, [tick])
    assert result.data_freshness == DataFreshness.FRESH
    assert result.quotes[0].age_seconds == pytest.approx(10.0)
    assert result.quotes[0].basis == FreshnessBasis.EXCHANGE


def test_naive_datetimes_treated_as_utc():
    now = datetime(2026, 10, 21, 5, 0, 0)  # naive
    exchange = datetime(2026, 10, 21, 4, 59, 50)
    result = _gate().evaluate(now, [_spot(exchange, now)])
    assert result.data_freshness == DataFreshness.FRESH
    assert result.quotes[0].age_seconds == pytest.approx(10.0)


def test_exchange_at_max_age_is_fresh_beyond_is_stale():
    now = _regular_now()
    at_limit = _spot(now - timedelta(seconds=30), now)
    past_limit = _spot(now - timedelta(seconds=30.01), now)
    assert _gate().evaluate(now, [at_limit]).data_freshness == DataFreshness.FRESH
    assert _gate().evaluate(now, [past_limit]).gate_reason == GateReason.STALE_DATA


@pytest.mark.asyncio
async def test_service_freshness_uses_clock_after_fetch_not_request_start(monkeypatch):
    """OptionPredictionService must not evaluate freshness with the pre-gather clock."""
    request_start = IST.localize(datetime(2026, 10, 21, 10, 30)).astimezone(timezone.utc)
    quote_time = request_start + timedelta(seconds=20)
    evaluation_time = request_start + timedelta(seconds=21)
    calls = {"n": 0}

    def fake_now(tz=None):
        calls["n"] += 1
        # 1: request_at; subsequent: post-fetch evaluation boundary
        if calls["n"] == 1:
            return request_start
        return evaluation_time

    class _Dt:
        timezone = timezone

        @staticmethod
        def now(tz=None):
            return fake_now(tz)

    monkeypatch.setattr(
        "services.prediction.option_prediction_service.datetime",
        _Dt,
    )

    spot = Tick(
        symbol="^NSEI",
        ltp=25100,
        prev_close=25000,
        change=100,
        change_pct=0.4,
        timestamp=quote_time,
        provider="ANGEL",
        fetched_at=quote_time,
        exchange_timestamp=quote_time,
    )
    service = _service(TradingCalendar(set()), _chain(quote_time, quote_time), spot)
    prediction = await service.predict(OptionUnderlying.NIFTY, date(2026, 10, 27))

    assert prediction.gate_reason != GateReason.UNKNOWN_FRESHNESS
    assert prediction.data_freshness == DataFreshness.FRESH
    assert all(q.verified for q in prediction.quote_timestamps)
    assert prediction.direction == PredictionDirection.CALL
    assert prediction.contract is not None
