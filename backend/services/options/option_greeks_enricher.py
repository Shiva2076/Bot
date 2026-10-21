from datetime import datetime, time
from typing import Optional

import pytz

from schemas.options import OptionChain, OptionChainRow, OptionPricingInput, OptionQuote, OptionType
from services.options.black_scholes_model import BlackScholesModel

IST = pytz.timezone("Asia/Kolkata")
EXPIRY_CLOSE = time(15, 30)
SECONDS_PER_YEAR = 365.0 * 24 * 3600


class OptionGreeksEnricher:
    """Fills IV and Greeks on every chain quote from its traded premium (mid when a valid two-sided quote exists)."""

    def __init__(self, model: BlackScholesModel, rate: float):
        self._model = model
        self._rate = rate

    def enrich(self, chain: OptionChain, now: datetime) -> OptionChain:
        expiry_at = IST.localize(datetime.combine(chain.expiry, EXPIRY_CLOSE))
        years = (expiry_at - now.astimezone(IST)).total_seconds() / SECONDS_PER_YEAR
        if years <= 0 or chain.spot <= 0:
            return chain
        rows = [
            OptionChainRow(
                strike=row.strike,
                call=self._enrich_quote(row.call, OptionType.CE, row.strike, chain.spot, years),
                put=self._enrich_quote(row.put, OptionType.PE, row.strike, chain.spot, years),
            )
            for row in chain.rows
        ]
        return chain.model_copy(update={"rows": rows})

    def _enrich_quote(
        self,
        quote: Optional[OptionQuote],
        option_type: OptionType,
        strike: float,
        spot: float,
        years: float,
    ) -> Optional[OptionQuote]:
        if quote is None:
            return None
        premium = self._premium(quote)
        if premium <= 0 or strike <= 0:
            return quote
        contract = OptionPricingInput(
            option_type=option_type, spot=spot, strike=strike, years_to_expiry=years, rate=self._rate
        )
        vol = self._model.implied_vol(contract, premium)
        if vol is None:
            return quote
        greeks = self._model.greeks(contract, vol)
        return quote.model_copy(update=greeks.model_dump())

    @staticmethod
    def _premium(quote: OptionQuote) -> float:
        if quote.bid and quote.ask and quote.ask >= quote.bid > 0:
            return (quote.bid + quote.ask) / 2.0
        return quote.ltp
