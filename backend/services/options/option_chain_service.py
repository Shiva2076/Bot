from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List

import pytz

from schemas.options import (
    OptionChain,
    OptionChainRow,
    OptionContract,
    OptionExpiries,
    OptionQuote,
    OptionType,
    OptionUnderlying,
)
from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.brokers.angel.provider import AngelProvider
from services.brokers.angel.quote_mapper import AngelQuoteMapper
from services.options.option_greeks_enricher import OptionGreeksEnricher
from services.trading.errors import UnknownInstrumentError
from services.trading.failover_market_data import FailoverMarketData

UNDERLYING_SPOT_SYMBOLS: Dict[OptionUnderlying, str] = {
    OptionUnderlying.NIFTY: "^NSEI",
    OptionUnderlying.BANKNIFTY: "^NSEBANK",
}


class OptionChainService:
    def __init__(
        self,
        master: AngelInstrumentMaster,
        angel: AngelProvider,
        market_data: FailoverMarketData,
        mapper: AngelQuoteMapper,
        greeks: OptionGreeksEnricher,
    ):
        self._master = master
        self._angel = angel
        self._market_data = market_data
        self._mapper = mapper
        self._greeks = greeks

    async def get_expiries(self, underlying: OptionUnderlying) -> OptionExpiries:
        return OptionExpiries(underlying=underlying, expiries=await self._master.expiries(underlying))

    async def get_chain(self, underlying: OptionUnderlying, expiry: date) -> OptionChain:
        contracts = await self._master.chain_contracts(underlying, expiry)
        if not contracts:
            raise UnknownInstrumentError(f"No {underlying.value} options expiring on {expiry.isoformat()}")
        quotes = await self._angel.get_quotes([c.symbol for c in contracts])
        spot = (await self._market_data.get_tick(UNDERLYING_SPOT_SYMBOLS[underlying])).ltp
        rows = self._build_rows(contracts, {
            c.symbol: self._mapper.to_option_quote(
                c, quotes[c.symbol], self._angel.quote_fetched_at(c.symbol)
            )
            for c in contracts if c.symbol in quotes
        })
        chain = OptionChain(
            underlying=underlying,
            expiry=expiry,
            spot=spot,
            atm_strike=min((r.strike for r in rows), key=lambda strike: abs(strike - spot)),
            lot_size=contracts[0].lot_size,
            rows=rows,
        )
        return self._greeks.enrich(chain, datetime.now(pytz.utc))

    def _build_rows(self, contracts: List[OptionContract], quotes: Dict[str, OptionQuote]) -> List[OptionChainRow]:
        by_strike: Dict[float, Dict[OptionType, OptionQuote]] = defaultdict(dict)
        for contract in contracts:
            if contract.symbol in quotes:
                by_strike[contract.strike][contract.option_type] = quotes[contract.symbol]
        return [
            OptionChainRow(strike=strike, call=legs.get(OptionType.CE), put=legs.get(OptionType.PE))
            for strike, legs in sorted(by_strike.items())
        ]
