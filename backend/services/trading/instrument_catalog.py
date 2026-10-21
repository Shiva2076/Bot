from typing import Dict, List

from config import Settings
from schemas.options import OptionUnderlying
from schemas.trading import Instrument, InstrumentKind
from services.market_data import NIFTY50_STOCKS
from services.trading.errors import UnknownInstrumentError

STOCK_LOT_SIZE = 1


class InstrumentCatalog:
    def __init__(self, settings: Settings):
        indices = [
            Instrument(
                symbol="^NSEI", name="NIFTY 50", kind=InstrumentKind.INDEX,
                lot_size=settings.nifty_lot_size, option_underlying=OptionUnderlying.NIFTY,
            ),
            Instrument(
                symbol="^NSEBANK", name="BANK NIFTY", kind=InstrumentKind.INDEX,
                lot_size=settings.banknifty_lot_size, option_underlying=OptionUnderlying.BANKNIFTY,
            ),
            Instrument(symbol="^BSESN", name="SENSEX", kind=InstrumentKind.INDEX, lot_size=settings.sensex_lot_size),
        ]
        stocks = [
            Instrument(symbol=s["symbol"], name=s["name"], kind=InstrumentKind.STOCK, lot_size=STOCK_LOT_SIZE)
            for s in NIFTY50_STOCKS
        ]
        self._instruments: Dict[str, Instrument] = {i.symbol: i for i in indices + stocks}

    def list_all(self) -> List[Instrument]:
        return list(self._instruments.values())

    def contains(self, symbol: str) -> bool:
        return symbol in self._instruments

    def get(self, symbol: str) -> Instrument:
        instrument = self._instruments.get(symbol)
        if instrument is None:
            raise UnknownInstrumentError(f"{symbol} is not a tradable instrument")
        return instrument
