from datetime import datetime
from typing import Optional

import pandas as pd
import pytz

from schemas.premarket import NiftyOpeningContext
from services.market_data import MarketDataService
from services.premarket.trading_calendar import TradingCalendar
from services.trading.errors import MarketDataUnavailableError
from services.trading.failover_market_data import FailoverMarketData

IST = pytz.timezone("Asia/Kolkata")
NIFTY_SYMBOL = "^NSEI"


class NiftyContextCollector:
    def __init__(
        self,
        market_data: FailoverMarketData,
        yahoo_history: MarketDataService,
        calendar: TradingCalendar,
    ):
        self._market_data = market_data
        self._yahoo_history = yahoo_history
        self._calendar = calendar

    async def collect(self) -> NiftyOpeningContext:
        phase = self._calendar.session_phase(self._calendar.now())
        try:
            tick = await self._market_data.get_tick(NIFTY_SYMBOL)
        except MarketDataUnavailableError:
            return NiftyOpeningContext(
                available=False,
                session_phase=phase,
                warning="NIFTY spot unavailable.",
            )
        history = await self._yahoo_history.fetch_ohlcv(NIFTY_SYMBOL, period="10d", interval="1d")
        previous_high, previous_low, support, resistance = self._levels(history, tick.prev_close)
        gap_pct = round((tick.ltp - tick.prev_close) / tick.prev_close * 100.0, 2) if tick.prev_close else None
        warning = (
            "Pre-open indicative auction price is not available from free providers; "
            "gap uses latest traded/indicative print vs previous close."
            if phase in {"PRE_MARKET", "PRE_OPEN"}
            else None
        )
        return NiftyOpeningContext(
            available=True,
            previous_close=tick.prev_close,
            last=tick.ltp,
            previous_high=previous_high,
            previous_low=previous_low,
            gap_pct=gap_pct,
            support=support,
            resistance=resistance,
            session_phase=phase,
            timestamp=tick.timestamp if isinstance(tick.timestamp, datetime) else datetime.now(IST),
            source=tick.provider,
            warning=warning,
        )

    @staticmethod
    def _levels(history: Optional[pd.DataFrame], previous_close: float):
        if history is None or history.empty:
            return None, None, round(previous_close * 0.995, 2), round(previous_close * 1.005, 2)
        frame = history.copy()
        for col in ["high", "low", "close"]:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
        previous = frame.iloc[-2] if len(frame) >= 2 else frame.iloc[-1]
        previous_high = round(float(previous["high"]), 2)
        previous_low = round(float(previous["low"]), 2)
        return previous_high, previous_low, previous_low, previous_high
