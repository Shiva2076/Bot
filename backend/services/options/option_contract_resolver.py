from typing import Optional

from schemas.options import OptionType, ParsedOptionSymbol
from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.options.option_symbol_parser import OptionSymbolParser


class OptionContractResolver:
    """Resolve option metadata from symbol parse, then Angel master (Sensex BFO weeklies)."""

    def __init__(self, parser: OptionSymbolParser, master: AngelInstrumentMaster):
        self._parser = parser
        self._master = master

    async def resolve(self, symbol: str) -> Optional[ParsedOptionSymbol]:
        parsed = self._parser.parse(symbol)
        if parsed is not None:
            return parsed
        contract = await self._master.option(symbol)
        if contract is None:
            return None
        return ParsedOptionSymbol(
            underlying=contract.underlying,
            expiry=contract.expiry,
            strike=contract.strike,
            option_type=OptionType(contract.option_type),
        )
