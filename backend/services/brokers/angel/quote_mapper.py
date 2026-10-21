from datetime import datetime
from typing import List, Optional, Tuple

import pytz

from schemas.angel import AngelDepthLevel, AngelQuote
from schemas.options import FuturesContract, FuturesQuote, OptionContract, OptionQuote
from schemas.trading import Candle, Tick
from services.trading.exchange_timestamp_validator import ExchangeTimestampValidator

IST = pytz.timezone("Asia/Kolkata")
EXCHANGE_TIME_FORMAT = "%d-%b-%Y %H:%M:%S"


class AngelQuoteMapper:
    def to_tick(self, symbol: str, quote: AngelQuote, provider: str, fetched_at: datetime) -> Tick:
        exchange_ts = self.parse_exchange_timestamp(quote)
        return Tick(
            symbol=symbol,
            ltp=quote.ltp,
            prev_close=quote.close,
            change=round(quote.net_change, 2),
            change_pct=round(quote.percent_change, 2),
            timestamp=exchange_ts if exchange_ts is not None else fetched_at,
            provider=provider,
            fetched_at=fetched_at,
            exchange_timestamp=exchange_ts,
        )

    def to_option_quote(
        self, contract: OptionContract, quote: AngelQuote, fetched_at: datetime
    ) -> OptionQuote:
        return OptionQuote(
            symbol=contract.symbol,
            display_name=contract.display_name,
            ltp=quote.ltp,
            change=round(quote.net_change, 2),
            change_pct=round(quote.percent_change, 2),
            open_interest=quote.open_interest,
            volume=quote.trade_volume,
            bid=self._best_price(quote.depth.buy) if quote.depth else None,
            ask=self._best_price(quote.depth.sell) if quote.depth else None,
            fetched_at=fetched_at,
            exchange_timestamp=self.parse_exchange_timestamp(quote),
        )

    def to_futures_quote(self, contract: FuturesContract, quote: AngelQuote) -> FuturesQuote:
        return FuturesQuote(
            symbol=contract.symbol,
            ltp=quote.ltp,
            open_interest=quote.open_interest,
            volume=quote.trade_volume,
            bid=self._best_price(quote.depth.buy) if quote.depth else None,
            ask=self._best_price(quote.depth.sell) if quote.depth else None,
        )

    def to_candle(self, row: Tuple[str, float, float, float, float, float]) -> Candle:
        timestamp, open_, high, low, close, volume = row
        return Candle(
            time=int(datetime.fromisoformat(timestamp).timestamp()),
            open=open_, high=high, low=low, close=close, volume=volume,
        )

    @staticmethod
    def parse_exchange_timestamp(quote: AngelQuote) -> Optional[datetime]:
        """Parse Angel FULL-mode exchange times. Never invent a timestamp from fetch time."""
        for raw in (quote.exch_trade_time, quote.exch_feed_time):
            parsed = AngelQuoteMapper._parse_angel_time(raw)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_angel_time(raw: Optional[str]) -> Optional[datetime]:
        if raw is None or not str(raw).strip():
            return None
        text = str(raw).strip()
        if text in {"0", "0.0"}:
            return None
        try:
            parsed = IST.localize(datetime.strptime(text, EXCHANGE_TIME_FORMAT))
        except (TypeError, ValueError):
            return None
        if not ExchangeTimestampValidator.is_plausible(parsed):
            return None
        return parsed

    def _best_price(self, levels: List[AngelDepthLevel]) -> Optional[float]:
        prices = [level.price for level in levels if level.price > 0]
        return prices[0] if prices else None
