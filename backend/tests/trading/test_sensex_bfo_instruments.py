import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import httpx
import pytz

from config import Settings
from schemas.options import OptionUnderlying
from services.brokers.angel.instrument_master import AngelInstrumentMaster
from services.options.option_symbol_parser import OptionSymbolParser
from services.trading.instrument_catalog import InstrumentCatalog

IST = pytz.timezone("Asia/Kolkata")
# Fixed wall clock before fixture weekly expiry (22OCT2026) so expiries() stays deterministic.
FIXED_NOW = IST.localize(datetime(2026, 10, 20, 12, 0, 0))


def test_catalog_exposes_sensex_option_underlying():
    sensex = InstrumentCatalog(Settings()).get("^BSESN")
    assert sensex.option_underlying == OptionUnderlying.SENSEX


def test_bfo_sensex_options_indexed_from_scrip_master(tmp_path: Path):
    cache = tmp_path / "scrip.json"
    cache.write_text(json.dumps([
        {
            "token": "1",
            "symbol": "SENSEX26O2269800CE",
            "name": "SENSEX",
            "expiry": "22OCT2026",
            "strike": "6980000.000000",
            "lotsize": "20",
            "instrumenttype": "OPTIDX",
            "exch_seg": "BFO",
            "tick_size": "5.000000",
        },
        {
            "token": "2",
            "symbol": "SENSEX26NOV72400PE",
            "name": "SENSEX",
            "expiry": "26NOV2026",
            "strike": "7240000.000000",
            "lotsize": "20",
            "instrumenttype": "OPTIDX",
            "exch_seg": "BFO",
            "tick_size": "5.000000",
        },
        {
            "token": "3",
            "symbol": "SENSEX26NOVFUT",
            "name": "SENSEX",
            "expiry": "26NOV2026",
            "strike": "0.000000",
            "lotsize": "20",
            "instrumenttype": "FUTIDX",
            "exch_seg": "BFO",
            "tick_size": "5.000000",
        },
    ]))

    async def run() -> None:
        transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("no network")))
        async with httpx.AsyncClient(transport=transport) as client:
            master = AngelInstrumentMaster(client, OptionSymbolParser(), cache_path=cache)
            with patch("services.brokers.angel.instrument_master.datetime") as mock_datetime:
                mock_datetime.now.return_value = FIXED_NOW
                mock_datetime.strptime = datetime.strptime
                expiries = await master.expiries(OptionUnderlying.SENSEX)
                assert expiries == [date(2026, 10, 22), date(2026, 11, 26)]
                weekly = await master.option("SENSEX26O2269800CE")
                assert weekly is not None
                assert weekly.underlying == OptionUnderlying.SENSEX
                assert weekly.expiry == date(2026, 10, 22)
                assert weekly.strike == 69800.0
                monthly = await master.option("SENSEX26NOV72400PE")
                assert monthly is not None
                assert monthly.expiry == date(2026, 11, 26)
                assert monthly.strike == 72400.0
                future = await master.near_future(OptionUnderlying.SENSEX)
                assert future is not None
                assert future.symbol == "SENSEX26NOVFUT"

    asyncio.run(run())
