from datetime import datetime
from typing import List

import pytz
import yfinance as yf

from schemas.trading import Candle

IST = pytz.timezone("Asia/Kolkata")


class YahooIntradayLoader:
    """Loads historical intraday bars for research backtests (Yahoo delayed/history limits apply)."""

    def load(self, symbol: str, period: str = "60d", interval: str = "5m") -> List[Candle]:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        if df is None or df.empty:
            return []
        candles: List[Candle] = []
        for ts, row in df.iterrows():
            when = ts.to_pydatetime()
            if when.tzinfo is None:
                when = pytz.utc.localize(when)
            candles.append(
                Candle(
                    time=int(when.timestamp()),
                    open=round(float(row["Open"]), 2),
                    high=round(float(row["High"]), 2),
                    low=round(float(row["Low"]), 2),
                    close=round(float(row["Close"]), 2),
                    volume=float(row["Volume"]),
                )
            )
        return candles
