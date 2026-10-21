from datetime import datetime
from typing import Dict, Optional

import pytz

from schemas.options import FuturesContract, OptionUnderlying
from schemas.prediction import FuturesFlowState
from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.brokers.angel.provider import AngelProvider
from services.brokers.angel.quote_mapper import AngelQuoteMapper

IST = pytz.timezone("Asia/Kolkata")


class FuturesFlowTracker:
    """Near-month index futures basis, OI/volume deltas and a tick-rule CVD proxy, reset each session."""

    def __init__(self, master: AngelInstrumentMaster, angel: AngelProvider, mapper: AngelQuoteMapper):
        self._master = master
        self._angel = angel
        self._mapper = mapper
        self._last: Dict[OptionUnderlying, FuturesFlowState] = {}

    def latest(self, underlying: OptionUnderlying) -> Optional[FuturesFlowState]:
        state = self._last.get(underlying)
        if state is None or state.captured_at.date() != datetime.now(IST).date():
            return None
        return state

    async def observe(self, underlying: OptionUnderlying, spot: float) -> Optional[FuturesFlowState]:
        contract = await self._master.near_future(underlying)
        if contract is None:
            return None
        quotes = await self._angel.get_quotes([contract.symbol])
        if contract.symbol not in quotes:
            return None
        quote = self._mapper.to_futures_quote(contract, quotes[contract.symbol])
        now = datetime.now(IST)
        previous = self._previous(underlying, contract, now)
        price_change = quote.ltp - previous.ltp if previous else None
        oi_change = quote.open_interest - previous.open_interest if previous else None
        volume_change = quote.volume - previous.volume if previous else None
        state = FuturesFlowState(
            underlying=underlying,
            contract_symbol=contract.symbol,
            expiry=contract.expiry,
            captured_at=now,
            ltp=quote.ltp,
            spot=spot,
            basis=round(quote.ltp - spot, 2),
            basis_pct=round((quote.ltp - spot) / spot * 100, 4),
            open_interest=quote.open_interest,
            volume=quote.volume,
            price_change=price_change,
            oi_change=oi_change,
            volume_change=volume_change,
            cvd_proxy=(previous.cvd_proxy if previous else 0.0) + self._signed_volume(price_change, volume_change),
        )
        self._last[underlying] = state
        return state

    def _previous(
        self, underlying: OptionUnderlying, contract: FuturesContract, now: datetime
    ) -> Optional[FuturesFlowState]:
        previous = self._last.get(underlying)
        if previous is None:
            return None
        if previous.contract_symbol != contract.symbol or previous.captured_at.date() != now.date():
            return None
        return previous

    @staticmethod
    def _signed_volume(price_change: Optional[float], volume_change: Optional[float]) -> float:
        if price_change is None or volume_change is None or volume_change <= 0 or price_change == 0:
            return 0.0
        return volume_change if price_change > 0 else -volume_change
