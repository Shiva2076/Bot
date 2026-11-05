from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
import pytz

from schemas.costs import CostConfig
from schemas.options import OptionQuote, OptionUnderlying
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.trading.paper_fill_model import PaperFillModel, PaperFillResult

IST = pytz.timezone("Asia/Kolkata")

DEFAULT_COSTS = PaperCostCalculator(
    CostConfig(
        brokerage_pct=0.03,
        brokerage_flat=20.0,
        exchange_txn_pct=0.00345,
        sebi_pct=0.0001,
        stamp_duty_buy_pct=0.015,
        stt_sell_pct=0.025,
        gst_pct=18.0,
        slippage_bps=5.0,
    )
)


def _quote(
    ltp: float = 100.0,
    bid: Optional[float] = 95.0,
    ask: Optional[float] = 100.0,
    volume: Optional[float] = 10000.0,
    exchange_ts: Optional[datetime] = None,
) -> OptionQuote:
    return OptionQuote(
        symbol="NIFTY29OCT2625200CE",
        display_name="NIFTY 25200 CE",
        ltp=ltp,
        change=2.5,
        change_pct=2.56,
        open_interest=500000.0,
        volume=volume if volume is not None else 0.0,
        bid=bid,
        ask=ask,
        exchange_timestamp=exchange_ts,
        fetched_at=exchange_ts,
    )


def test_valid_quote_buy_fill_applies_slippage_and_costs_once():
    now = datetime(2026, 10, 23, 10, 0, 10, tzinfo=timezone.utc)
    ex_ts = now - timedelta(seconds=5)
    quote = _quote(ltp=100.0, bid=95.0, ask=100.0, volume=25000.0, exchange_ts=ex_ts)
    model = PaperFillModel(DEFAULT_COSTS, max_spread_pct=10.0, max_data_age_seconds=30.0)

    result = model.evaluate_buy_fill(quote, quantity=65, evaluation_time=now)

    assert result.success is True
    assert result.rejection_reasons == []
    assert result.reference_price == 100.0
    # Slippage: 5 bps on 100.0 = 100.05
    assert result.slipped_fill_price == 100.05
    assert result.quantity == 65
    # Notional = 100.05 * 65 = 6503.25
    assert result.total_notional == 6503.25
    assert result.costs is not None
    assert result.costs.slipped_price == 100.05
    assert result.costs.brokerage == 20.0  # Flat minimum
    assert result.costs.total_fees > 20.0
    assert result.total_cash_required == round(6503.25 + result.costs.total_fees, 2)
    assert result.spread_pct == 5.0  # (100 - 95)/100 * 100


def test_missing_and_zero_bid_ask_rejected():
    now = datetime(2026, 10, 23, 10, 0, 10, tzinfo=timezone.utc)
    model = PaperFillModel(DEFAULT_COSTS)

    # Missing ask
    res1 = model.evaluate_buy_fill(_quote(ask=None, bid=95.0, exchange_ts=now), quantity=65, evaluation_time=now)
    assert res1.success is False
    assert any("ask price" in r for r in res1.rejection_reasons)

    # Missing bid
    res2 = model.evaluate_buy_fill(_quote(ask=100.0, bid=None, exchange_ts=now), quantity=65, evaluation_time=now)
    assert res2.success is False
    assert any("bid price" in r for r in res2.rejection_reasons)

    # Zero or negative ask
    res3 = model.evaluate_buy_fill(_quote(ask=0.0, bid=95.0, exchange_ts=now), quantity=65, evaluation_time=now)
    assert res3.success is False
    assert any("ask price" in r for r in res3.rejection_reasons)

    # Zero or negative bid
    res4 = model.evaluate_buy_fill(_quote(ask=100.0, bid=-5.0, exchange_ts=now), quantity=65, evaluation_time=now)
    assert res4.success is False
    assert any("bid price" in r for r in res4.rejection_reasons)


def test_crossed_quotes_rejected():
    now = datetime(2026, 10, 23, 10, 0, 10, tzinfo=timezone.utc)
    model = PaperFillModel(DEFAULT_COSTS)
    quote = _quote(ask=100.0, bid=105.0, exchange_ts=now)

    res = model.evaluate_buy_fill(quote, quantity=65, evaluation_time=now)
    assert res.success is False
    assert any("Crossed market quotes" in r for r in res.rejection_reasons)


@pytest.mark.parametrize("bid,ask,expected_pass", [
    (90.01, 100.0, True),   # 9.99% spread <= 10.0%
    (90.00, 100.0, True),   # 10.00% spread == 10.0% boundary
    (89.99, 100.0, False),  # 10.01% spread > 10.0% boundary
    (80.00, 100.0, False),  # 20.00% spread > 10.0%
])
def test_spread_boundary_confirmation(bid: float, ask: float, expected_pass: bool):
    now = datetime(2026, 10, 23, 10, 0, 10, tzinfo=timezone.utc)
    model = PaperFillModel(DEFAULT_COSTS, max_spread_pct=10.0)
    quote = _quote(ask=ask, bid=bid, exchange_ts=now)

    res = model.evaluate_buy_fill(quote, quantity=65, evaluation_time=now)
    if expected_pass:
        assert res.success is True
    else:
        assert res.success is False
        assert any("spread too wide" in r.lower() for r in res.rejection_reasons)


def test_zero_and_missing_volume_rejected():
    now = datetime(2026, 10, 23, 10, 0, 10, tzinfo=timezone.utc)
    model = PaperFillModel(DEFAULT_COSTS)

    res_zero = model.evaluate_buy_fill(_quote(volume=0.0, exchange_ts=now), quantity=65, evaluation_time=now)
    assert res_zero.success is False
    assert any("illiquid" in r.lower() or "volume" in r.lower() for r in res_zero.rejection_reasons)

    res_neg = model.evaluate_buy_fill(_quote(volume=-100.0, exchange_ts=now), quantity=65, evaluation_time=now)
    assert res_neg.success is False
    assert any("illiquid" in r.lower() or "volume" in r.lower() for r in res_neg.rejection_reasons)


def test_exchange_timestamp_freshness_and_stale_rejection():
    now = datetime(2026, 10, 23, 10, 0, 30, tzinfo=timezone.utc)
    model = PaperFillModel(DEFAULT_COSTS, max_data_age_seconds=30.0, max_future_skew_seconds=5.0)

    # Missing timestamp
    res_none = model.evaluate_buy_fill(_quote(exchange_ts=None), quantity=65, evaluation_time=now)
    assert res_none.success is False
    assert any("Missing verified exchange timestamp" in r for r in res_none.rejection_reasons)

    # Implausible timestamp (year 1970)
    implausible = datetime(1970, 1, 1, 5, 30, tzinfo=timezone.utc)
    res_impl = model.evaluate_buy_fill(_quote(exchange_ts=implausible), quantity=65, evaluation_time=now)
    assert res_impl.success is False
    assert any("implausible" in r.lower() for r in res_impl.rejection_reasons)

    # Stale timestamp (age = 35s > 30s)
    stale_ts = now - timedelta(seconds=35)
    res_stale = model.evaluate_buy_fill(_quote(exchange_ts=stale_ts), quantity=65, evaluation_time=now)
    assert res_stale.success is False
    assert any("stale" in r.lower() for r in res_stale.rejection_reasons)

    # Future timestamp beyond 5s tolerance (10s in future)
    future_ts = now + timedelta(seconds=10)
    res_future = model.evaluate_buy_fill(_quote(exchange_ts=future_ts), quantity=65, evaluation_time=now)
    assert res_future.success is False
    assert any("future" in r.lower() for r in res_future.rejection_reasons)

    # Future timestamp within 5s tolerance (2s in future) -> acceptable
    minor_future_ts = now + timedelta(seconds=2)
    res_minor = model.evaluate_buy_fill(_quote(exchange_ts=minor_future_ts), quantity=65, evaluation_time=now)
    assert res_minor.success is True


def test_timezone_conversion_ist_and_utc():
    # 15:30 IST is 10:00 UTC
    now_utc = datetime(2026, 10, 23, 10, 0, 10, tzinfo=timezone.utc)
    ex_ist = IST.localize(datetime(2026, 10, 23, 15, 30, 5))  # 10:00:05 UTC (5s age)
    model = PaperFillModel(DEFAULT_COSTS)

    res = model.evaluate_buy_fill(_quote(exchange_ts=ex_ist), quantity=65, evaluation_time=now_utc)
    assert res.success is True
    assert res.rejection_reasons == []


def test_missing_quote_and_invalid_quantity():
    now = datetime(2026, 10, 23, 10, 0, 10, tzinfo=timezone.utc)
    model = PaperFillModel(DEFAULT_COSTS)

    res1 = model.evaluate_buy_fill(None, quantity=65, evaluation_time=now)
    assert res1.success is False
    assert any("missing" in r.lower() for r in res1.rejection_reasons)

    res2 = model.evaluate_buy_fill(_quote(exchange_ts=now), quantity=0, evaluation_time=now)
    assert res2.success is False
    assert any("quantity" in r.lower() for r in res2.rejection_reasons)


@pytest.mark.parametrize("underlying,symbol,token,exchange,lot_size", [
    (OptionUnderlying.NIFTY, "NIFTY29OCT2625200CE", "12345", "NFO", 65),
    (OptionUnderlying.BANKNIFTY, "BANKNIFTY29OCT2652000CE", "23456", "NFO", 30),
    (OptionUnderlying.SENSEX, "SENSEX29OCT2682000CE", "34567", "BFO", 10),
])
def test_provider_quote_mapping_for_nifty_banknifty_sensex_fails_closed(
    underlying: OptionUnderlying, symbol: str, token: str, exchange: str, lot_size: int
):
    from datetime import date
    from schemas.angel import AngelDepth, AngelDepthLevel, AngelQuote
    from schemas.options import OptionContract, OptionType, OptionUnderlying
    from services.brokers.angel.quote_mapper import AngelQuoteMapper

    mapper = AngelQuoteMapper()
    contract = OptionContract(
        symbol=symbol,
        token=token,
        underlying=underlying,
        expiry=date(2026, 10, 29),
        strike=25000.0,
        option_type=OptionType.CE,
        lot_size=lot_size,
        display_name=f"{symbol} CE",
    )

    now_ist_str = "23-Oct-2026 15:30:00"
    eval_time = IST.localize(datetime(2026, 10, 23, 15, 30, 5))
    fetched_at = IST.localize(datetime(2026, 10, 23, 15, 30, 6))

    # 1. Full quote from provider: valid bid, ask, volume, exchange timestamp
    angel_full = AngelQuote(
        exchange=exchange,
        tradingSymbol=symbol,
        symbolToken=token,
        ltp=150.0,
        close=145.0,
        netChange=5.0,
        percentChange=3.45,
        opnInterest=50000.0,
        tradeVolume=12000.0,
        exchFeedTime=now_ist_str,
        depth=AngelDepth(
            buy=[AngelDepthLevel(price=149.5, quantity=500)],
            sell=[AngelDepthLevel(price=150.0, quantity=500)],
        ),
    )
    quote = mapper.to_option_quote(contract, angel_full, fetched_at=fetched_at)
    assert quote.bid == 149.5
    assert quote.ask == 150.0
    assert quote.volume == 12000.0
    assert quote.exchange_timestamp is not None
    assert quote.fetched_at == fetched_at

    model = PaperFillModel(DEFAULT_COSTS)
    res = model.evaluate_buy_fill(quote, quantity=lot_size, evaluation_time=eval_time)
    assert res.success is True
    assert res.reference_price == 150.0
    assert res.costs is not None

    # 2. Provider returns quote without depth -> bid & ask must be None -> fail closed
    angel_no_depth = AngelQuote(
        exchange=exchange,
        tradingSymbol=symbol,
        symbolToken=token,
        ltp=150.0,
        close=145.0,
        netChange=5.0,
        percentChange=3.45,
        opnInterest=50000.0,
        tradeVolume=12000.0,
        exchFeedTime=now_ist_str,
        depth=None,
    )
    quote_no_depth = mapper.to_option_quote(contract, angel_no_depth, fetched_at=fetched_at)
    assert quote_no_depth.bid is None
    assert quote_no_depth.ask is None
    res_no_depth = model.evaluate_buy_fill(quote_no_depth, quantity=lot_size, evaluation_time=eval_time)
    assert res_no_depth.success is False
    assert any("ask price" in r for r in res_no_depth.rejection_reasons)

    # 3. Provider returns quote without exchange timestamp -> never fabricate from fetched_at -> fail closed
    angel_no_ts = AngelQuote(
        exchange=exchange,
        tradingSymbol=symbol,
        symbolToken=token,
        ltp=150.0,
        close=145.0,
        netChange=5.0,
        percentChange=3.45,
        opnInterest=50000.0,
        tradeVolume=12000.0,
        exchFeedTime=None,
        exchTradeTime=None,
        depth=AngelDepth(
            buy=[AngelDepthLevel(price=149.5, quantity=500)],
            sell=[AngelDepthLevel(price=150.0, quantity=500)],
        ),
    )
    quote_no_ts = mapper.to_option_quote(contract, angel_no_ts, fetched_at=fetched_at)
    assert quote_no_ts.exchange_timestamp is None  # NOT fabricated from fetched_at!
    res_no_ts = model.evaluate_buy_fill(quote_no_ts, quantity=lot_size, evaluation_time=eval_time)
    assert res_no_ts.success is False
    assert any("Missing verified exchange timestamp" in r for r in res_no_ts.rejection_reasons)

    # 4. Provider returns zero volume -> fail closed
    angel_zero_vol = AngelQuote(
        exchange=exchange,
        tradingSymbol=symbol,
        symbolToken=token,
        ltp=150.0,
        close=145.0,
        netChange=5.0,
        percentChange=3.45,
        opnInterest=50000.0,
        tradeVolume=0.0,
        exchFeedTime=now_ist_str,
        depth=AngelDepth(
            buy=[AngelDepthLevel(price=149.5, quantity=500)],
            sell=[AngelDepthLevel(price=150.0, quantity=500)],
        ),
    )
    quote_zero_vol = mapper.to_option_quote(contract, angel_zero_vol, fetched_at=fetched_at)
    assert quote_zero_vol.volume == 0.0
    res_zero_vol = model.evaluate_buy_fill(quote_zero_vol, quantity=lot_size, evaluation_time=eval_time)
    assert res_zero_vol.success is False
    assert any("volume" in r.lower() for r in res_zero_vol.rejection_reasons)

