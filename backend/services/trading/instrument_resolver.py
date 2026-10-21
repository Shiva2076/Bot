from schemas.trading import Instrument, InstrumentKind
from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.trading.errors import UnknownInstrumentError
from services.trading.instrument_catalog import InstrumentCatalog


class InstrumentResolver:
    def __init__(self, catalog: InstrumentCatalog, master: AngelInstrumentMaster):
        self._catalog = catalog
        self._master = master

    async def resolve(self, symbol: str) -> Instrument:
        if self._catalog.contains(symbol):
            return self._catalog.get(symbol)
        contract = await self._master.option(symbol)
        if contract is None:
            raise UnknownInstrumentError(f"{symbol} is not a tradable instrument")
        return Instrument(
            symbol=contract.symbol,
            name=contract.display_name,
            kind=InstrumentKind.OPTION,
            lot_size=contract.lot_size,
            option_underlying=contract.underlying,
        )
