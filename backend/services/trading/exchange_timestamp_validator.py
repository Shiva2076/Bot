from datetime import datetime

import pytz

IST = pytz.timezone("Asia/Kolkata")
_MIN_PLAUSIBLE_EXCHANGE_YEAR = 2000


class ExchangeTimestampValidator:
    """Rejects epoch sentinels and other non-exchange timestamps."""

    @staticmethod
    def is_plausible(value: datetime) -> bool:
        try:
            epoch_seconds = value.timestamp()
        except (OverflowError, OSError, ValueError):
            return False
        if epoch_seconds <= 0:
            return False
        return value.astimezone(IST).year >= _MIN_PLAUSIBLE_EXCHANGE_YEAR
