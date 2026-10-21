import asyncio
from pathlib import Path

import httpx
import pytest

from schemas.options import OptionUnderlying
from services.brokers.angel.instrument_master import INDEX_REFS, AngelInstrumentMaster
from services.options.option_symbol_parser import OptionSymbolParser
from services.trading.errors import MarketDataUnavailableError


def test_index_ref_does_not_download_scrip_master(tmp_path: Path):
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="should not be called")

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            master = AngelInstrumentMaster(client, OptionSymbolParser(), cache_path=tmp_path / "scrip.json")
            ref = await master.ref_for("^NSEI")
            assert ref == INDEX_REFS["^NSEI"]
            assert calls["n"] == 0

    asyncio.run(run())


def test_missing_cache_fails_fast_and_starts_warm(tmp_path: Path):
    async def hang(request: httpx.Request):
        await asyncio.sleep(60)
        return httpx.Response(200, content=b"[]")

    async def run() -> None:
        transport = httpx.MockTransport(hang)
        async with httpx.AsyncClient(transport=transport) as client:
            master = AngelInstrumentMaster(client, OptionSymbolParser(), cache_path=tmp_path / "scrip.json")
            with pytest.raises(MarketDataUnavailableError, match="downloading"):
                await master.expiries(OptionUnderlying.NIFTY)
            assert master._warm_task is not None
            master._warm_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await master._warm_task

    asyncio.run(run())


def test_cache_serves_immediately(tmp_path: Path):
    cache = tmp_path / "scrip.json"
    cache.write_text("[]")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network should not be required for cached load")

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            master = AngelInstrumentMaster(client, OptionSymbolParser(), cache_path=cache)
            expiries = await master.expiries(OptionUnderlying.NIFTY)
            assert expiries == []

    asyncio.run(run())
