import asyncio
from datetime import date
from typing import Dict, List, Optional

from schemas.options import FuturesContract, FuturesQuote, OptionUnderlying
from services.prediction.futures_flow_tracker import FuturesFlowTracker

CONTRACT = FuturesContract(
    symbol="NIFTY27OCT26FUT", token="1", underlying=OptionUnderlying.NIFTY, expiry=date(2026, 10, 27), lot_size=65
)


class FakeMaster:
    async def near_future(self, underlying: OptionUnderlying) -> Optional[FuturesContract]:
        return CONTRACT


class FakeAngel:
    def __init__(self, quotes: List[FuturesQuote]):
        self._quotes = quotes

    async def get_quotes(self, symbols: List[str]) -> Dict[str, FuturesQuote]:
        return {CONTRACT.symbol: self._quotes.pop(0)}


class PassThroughMapper:
    def to_futures_quote(self, contract: FuturesContract, quote: FuturesQuote) -> FuturesQuote:
        return quote


def _quote(ltp: float, oi: float, volume: float) -> FuturesQuote:
    return FuturesQuote(symbol=CONTRACT.symbol, ltp=ltp, open_interest=oi, volume=volume, bid=None, ask=None)


def test_deltas_basis_and_cvd_proxy():
    angel = FakeAngel([_quote(25100.0, 1000.0, 500.0), _quote(25110.0, 1100.0, 800.0), _quote(25105.0, 1150.0, 900.0)])
    tracker = FuturesFlowTracker(FakeMaster(), angel, PassThroughMapper())
    first = asyncio.run(tracker.observe(OptionUnderlying.NIFTY, 25000.0))
    assert first.basis == 100.0 and first.price_change is None and first.cvd_proxy == 0.0
    second = asyncio.run(tracker.observe(OptionUnderlying.NIFTY, 25000.0))
    assert second.oi_change == 100.0 and second.volume_change == 300.0 and second.cvd_proxy == 300.0
    third = asyncio.run(tracker.observe(OptionUnderlying.NIFTY, 25000.0))
    assert third.cvd_proxy == 200.0
    assert tracker.latest(OptionUnderlying.NIFTY) == third
