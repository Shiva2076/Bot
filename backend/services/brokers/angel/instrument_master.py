import asyncio
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
import pytz
from pydantic import TypeAdapter, ValidationError

from schemas.angel import AngelInstrumentRef, AngelScrip
from schemas.options import FuturesContract, OptionContract, OptionType, OptionUnderlying, ParsedOptionSymbol
from services.options.option_symbol_parser import OptionSymbolParser
from services.trading.errors import MarketDataUnavailableError

SCRIP_MASTER_URLS = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json",
)
INDEX_REFS: Dict[str, AngelInstrumentRef] = {
    "^NSEI": AngelInstrumentRef(exchange="NSE", token="99926000"),
    "^NSEBANK": AngelInstrumentRef(exchange="NSE", token="99926009"),
    "^BSESN": AngelInstrumentRef(exchange="BSE", token="99919000"),
    "^INDIAVIX": AngelInstrumentRef(exchange="NSE", token="99926017"),
}
EQUITY_SUFFIX = "-EQ"
YAHOO_NSE_SUFFIX = ".NS"
OPTION_SEGMENT = "NFO"
OPTION_INSTRUMENT_TYPE = "OPTIDX"
FUTURES_INSTRUMENT_TYPE = "FUTIDX"
FUTURES_UNDERLYINGS = {u.value: u for u in OptionUnderlying}
ANGEL_STRIKE_MULTIPLIER = 100
IST = pytz.timezone("Asia/Kolkata")
DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[3] / ".cache" / "angel_scrip_master.json"
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_TIMEOUT_SECONDS = 180.0

_scrip_list_adapter = TypeAdapter(List[AngelScrip])


class AngelInstrumentIndex:
    def __init__(
        self,
        refs: Dict[str, AngelInstrumentRef],
        options: Dict[str, OptionContract],
        futures: List[FuturesContract],
    ):
        self.refs = refs
        self.options = options
        self.chains: Dict[Tuple[OptionUnderlying, date], List[OptionContract]] = defaultdict(list)
        for contract in options.values():
            self.chains[(contract.underlying, contract.expiry)].append(contract)
        self.futures: Dict[OptionUnderlying, List[FuturesContract]] = defaultdict(list)
        for future in sorted(futures, key=lambda f: f.expiry):
            self.futures[future.underlying].append(future)


class AngelInstrumentMaster:
    def __init__(
        self,
        client: httpx.AsyncClient,
        parser: OptionSymbolParser,
        cache_path: Path = DEFAULT_CACHE_PATH,
    ):
        self._client = client
        self._parser = parser
        self._cache_path = cache_path
        self._index: Optional[AngelInstrumentIndex] = None
        self._loaded_on: Optional[date] = None
        self._lock: Optional[asyncio.Lock] = None
        self._warm_task: Optional[asyncio.Task] = None

    async def ref_for(self, symbol: str) -> Optional[AngelInstrumentRef]:
        # Hardcoded index tokens must not wait on the 30MB+ scrip master download.
        if symbol in INDEX_REFS:
            return INDEX_REFS[symbol]
        index = await self._ensure_loaded()
        return index.refs.get(symbol)

    async def option(self, symbol: str) -> Optional[OptionContract]:
        index = await self._ensure_loaded()
        return index.options.get(symbol)

    async def expiries(self, underlying: OptionUnderlying) -> List[date]:
        index = await self._ensure_loaded()
        today = datetime.now(IST).date()
        return sorted(expiry for u, expiry in index.chains if u == underlying and expiry >= today)

    async def chain_contracts(self, underlying: OptionUnderlying, expiry: date) -> List[OptionContract]:
        index = await self._ensure_loaded()
        return index.chains.get((underlying, expiry), [])

    async def near_future(self, underlying: OptionUnderlying) -> Optional[FuturesContract]:
        index = await self._ensure_loaded()
        today = datetime.now(IST).date()
        return next((f for f in index.futures.get(underlying, []) if f.expiry >= today), None)

    def start_warm(self) -> None:
        """Kick off background download/refresh; safe to call from app startup."""
        if self._warm_task is not None and not self._warm_task.done():
            return
        self._warm_task = asyncio.create_task(self._warm())

    async def _warm(self) -> None:
        try:
            await self._refresh_from_network()
        except Exception as exc:
            print(f"Angel instrument master warm failed: {exc}")

    async def _ensure_loaded(self) -> AngelInstrumentIndex:
        self._lock = self._lock or asyncio.Lock()
        async with self._lock:
            today = datetime.now(IST).date()
            if self._index is not None and self._loaded_on == today:
                return self._index
            cached = self._read_cache_file()

        if cached is not None:
            try:
                index = await asyncio.get_running_loop().run_in_executor(None, self._build_index, cached)
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                self._cache_path.unlink(missing_ok=True)
                self.start_warm()
                raise MarketDataUnavailableError(
                    f"Angel instrument cache was corrupt and is being re-downloaded: {e}"
                ) from e
            cache_day = datetime.fromtimestamp(self._cache_path.stat().st_mtime, IST).date()
            async with self._lock:
                self._index = index
                self._loaded_on = today
            if cache_day != today:
                self.start_warm()
            return index

        self.start_warm()
        raise MarketDataUnavailableError(
            "Angel instrument master is downloading; retry option chain in a moment."
        )

    async def _refresh_from_network(self) -> None:
        raw = await self._download_bytes()
        self._write_cache(raw)
        index = await asyncio.get_running_loop().run_in_executor(None, self._build_index, raw)
        self._lock = self._lock or asyncio.Lock()
        async with self._lock:
            self._index = index
            self._loaded_on = datetime.now(IST).date()

    async def _download_bytes(self) -> bytes:
        last_error: Optional[Exception] = None
        for url in SCRIP_MASTER_URLS:
            try:
                raw = await asyncio.get_running_loop().run_in_executor(
                    None, self._curl_download, url
                )
                if raw is not None:
                    return raw
            except Exception as e:
                last_error = e
        timeout = httpx.Timeout(DOWNLOAD_TIMEOUT_SECONDS, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, http2=False) as client:
            for url in SCRIP_MASTER_URLS:
                for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
                    try:
                        async with client.stream("GET", url) as response:
                            response.raise_for_status()
                            chunks: List[bytes] = []
                            async for chunk in response.aiter_bytes():
                                chunks.append(chunk)
                            raw = b"".join(chunks)
                        if len(raw) < 1_000_000:
                            raise MarketDataUnavailableError(
                                f"Angel scrip master too small ({len(raw)} bytes)"
                            )
                        return raw
                    except (httpx.HTTPError, MarketDataUnavailableError) as e:
                        last_error = e
                        await asyncio.sleep(min(2 * attempt, 6))
        cached = self._read_cache_file()
        if cached is not None:
            return cached
        raise MarketDataUnavailableError(
            f"Could not download Angel One instrument list: {last_error}"
        ) from last_error

    def _curl_download(self, url: str) -> Optional[bytes]:
        """Resume-friendly download; Angel CDN often drops mid-transfer on HTTP/2."""
        import subprocess

        tmp = self._cache_path.with_suffix(".json.partial")
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(DOWNLOAD_ATTEMPTS):
            result = subprocess.run(
                [
                    "curl",
                    "--http1.1",
                    "-L",
                    "-C",
                    "-",
                    "--fail",
                    "--retry",
                    "2",
                    "--retry-delay",
                    "2",
                    "--connect-timeout",
                    "30",
                    "--max-time",
                    str(int(DOWNLOAD_TIMEOUT_SECONDS)),
                    "-A",
                    "Mozilla/5.0",
                    "-o",
                    str(tmp),
                    url,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 1_000_000:
                continue
            raw = tmp.read_bytes()
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                tmp.unlink(missing_ok=True)
                continue
            return raw
        return None

    def _read_cache_file(self) -> Optional[bytes]:
        if not self._cache_path.is_file():
            return None
        return self._cache_path.read_bytes()

    def _write_cache(self, raw: bytes) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path.with_suffix(".json.tmp")
        tmp.write_bytes(raw)
        tmp.replace(self._cache_path)

    def _build_index(self, raw: bytes) -> AngelInstrumentIndex:
        refs: Dict[str, AngelInstrumentRef] = dict(INDEX_REFS)
        options: Dict[str, OptionContract] = {}
        futures: List[FuturesContract] = []
        for scrip in _scrip_list_adapter.validate_json(raw):
            if scrip.exch_seg == "NSE" and scrip.symbol.endswith(EQUITY_SUFFIX):
                refs[f"{scrip.symbol[:-len(EQUITY_SUFFIX)]}{YAHOO_NSE_SUFFIX}"] = AngelInstrumentRef(
                    exchange=scrip.exch_seg, token=scrip.token
                )
            elif scrip.exch_seg == OPTION_SEGMENT and scrip.instrumenttype == OPTION_INSTRUMENT_TYPE:
                parsed = self._parser.parse(scrip.symbol)
                if parsed:
                    options[scrip.symbol] = self._to_contract(scrip, parsed)
                    refs[scrip.symbol] = AngelInstrumentRef(exchange=scrip.exch_seg, token=scrip.token)
            elif (
                scrip.exch_seg == OPTION_SEGMENT
                and scrip.instrumenttype == FUTURES_INSTRUMENT_TYPE
                and scrip.name in FUTURES_UNDERLYINGS
            ):
                futures.append(self._to_future(scrip))
                refs[scrip.symbol] = AngelInstrumentRef(exchange=scrip.exch_seg, token=scrip.token)
        return AngelInstrumentIndex(refs, options, futures)

    @staticmethod
    def _to_future(scrip: AngelScrip) -> FuturesContract:
        return FuturesContract(
            symbol=scrip.symbol,
            token=scrip.token,
            underlying=FUTURES_UNDERLYINGS[scrip.name],
            expiry=datetime.strptime(scrip.expiry, "%d%b%Y").date(),
            lot_size=int(float(scrip.lotsize)),
        )

    def _to_contract(self, scrip: AngelScrip, parsed: ParsedOptionSymbol) -> OptionContract:
        return OptionContract(
            symbol=scrip.symbol,
            token=scrip.token,
            underlying=parsed.underlying,
            expiry=datetime.strptime(scrip.expiry, "%d%b%Y").date(),
            strike=float(scrip.strike) / ANGEL_STRIKE_MULTIPLIER,
            option_type=OptionType(parsed.option_type),
            lot_size=int(float(scrip.lotsize)),
            display_name=self._parser.display_name(parsed),
        )
