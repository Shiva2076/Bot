"""
Read-only tick timestamp diagnostic. Prints timestamp fields only — never credentials,
tokens, PINs or TOTP secrets.

Usage (from backend/):  venv/bin/python -m scripts.diagnose_tick_timestamps ^NSEI RELIANCE.NS
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.trading import Tick  # noqa: E402
from services.brokers.angel.quote_mapper import AngelQuoteMapper  # noqa: E402
from services.trading.yahoo_provider import YahooProvider  # noqa: E402

DEFAULT_SYMBOLS = ["^NSEI", "RELIANCE.NS"]


class TickTimestampReport(BaseModel):
    symbol: str
    provider: str
    raw_exch_trade_time: Optional[str] = None
    raw_exch_feed_time: Optional[str] = None
    parsed_trade_time: Optional[datetime] = None
    parsed_feed_time: Optional[datetime] = None
    discarded_fields: List[str] = []
    exchange_timestamp: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    tick_timestamp: Optional[datetime] = None
    tick_timestamp_basis: str = "NONE"
    exchange_age_seconds: Optional[float] = None
    fetch_age_seconds: Optional[float] = None
    error: Optional[str] = None


class TickTimestampDiagnostic:
    def __init__(self, angel_provider, yahoo: YahooProvider, market_data):
        self._angel = angel_provider
        self._yahoo = yahoo
        self._market_data = market_data

    async def run(self, symbols: List[str]) -> List[TickTimestampReport]:
        reports: List[TickTimestampReport] = []
        for symbol in symbols:
            reports.append(await self._angel_report(symbol))
            reports.append(await self._yahoo_report(symbol))
            reports.append(await self._market_data_report(symbol))
        return reports

    async def _angel_report(self, symbol: str) -> TickTimestampReport:
        try:
            quotes = await self._angel.get_quotes([symbol])
        except Exception as exc:
            return TickTimestampReport(symbol=symbol, provider="ANGEL", error=type(exc).__name__)
        quote = quotes.get(symbol)
        if quote is None:
            return TickTimestampReport(symbol=symbol, provider="ANGEL", error="no quote returned")
        trade = AngelQuoteMapper.parse_angel_time(quote.exch_trade_time)
        feed = AngelQuoteMapper.parse_angel_time(quote.exch_feed_time)
        discarded = [
            name for name, raw, parsed in (
                ("exchTradeTime", quote.exch_trade_time, trade),
                ("exchFeedTime", quote.exch_feed_time, feed),
            ) if raw is not None and parsed is None
        ]
        tick = AngelQuoteMapper().to_tick(symbol, quote, "ANGEL", self._angel.quote_fetched_at(symbol))
        report = self._from_tick(symbol, "ANGEL", tick)
        return report.model_copy(update={
            "raw_exch_trade_time": quote.exch_trade_time,
            "raw_exch_feed_time": quote.exch_feed_time,
            "parsed_trade_time": trade,
            "parsed_feed_time": feed,
            "discarded_fields": discarded,
        })

    async def _yahoo_report(self, symbol: str) -> TickTimestampReport:
        try:
            tick = await self._yahoo.get_tick(symbol)
        except Exception as exc:
            return TickTimestampReport(symbol=symbol, provider="YAHOO", error=type(exc).__name__)
        if tick is None:
            return TickTimestampReport(symbol=symbol, provider="YAHOO", error="no tick / unsupported symbol")
        return self._from_tick(symbol, "YAHOO", tick)

    async def _market_data_report(self, symbol: str) -> TickTimestampReport:
        try:
            tick = await self._market_data.get_tick(symbol)
        except Exception as exc:
            return TickTimestampReport(symbol=symbol, provider="FAILOVER", error=type(exc).__name__)
        return self._from_tick(symbol, f"FAILOVER->{tick.provider}", tick)

    @staticmethod
    def _from_tick(symbol: str, provider: str, tick: Tick) -> TickTimestampReport:
        now = datetime.now(timezone.utc)
        exchange = tick.exchange_timestamp
        if exchange is not None and tick.timestamp == exchange:
            basis = "EXCHANGE"
        elif tick.fetched_at is not None and tick.timestamp == tick.fetched_at:
            basis = "FETCH"
        else:
            basis = "OTHER"
        return TickTimestampReport(
            symbol=symbol,
            provider=provider,
            exchange_timestamp=exchange,
            fetched_at=tick.fetched_at,
            tick_timestamp=tick.timestamp,
            tick_timestamp_basis=basis,
            exchange_age_seconds=None if exchange is None else round((now - exchange).total_seconds(), 2),
            fetch_age_seconds=None if tick.fetched_at is None else round((now - tick.fetched_at).total_seconds(), 2),
        )


async def _main(symbols: List[str]) -> None:
    from services.trading.providers import angel_provider, market_data

    diagnostic = TickTimestampDiagnostic(angel_provider, YahooProvider(0.0), market_data)
    for report in await diagnostic.run(symbols):
        print(report.model_dump_json())


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:] or DEFAULT_SYMBOLS))
