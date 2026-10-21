from datetime import datetime, time

import pytz

from schemas.options import OptionType, ParsedOptionSymbol

IST = pytz.timezone("Asia/Kolkata")
MARKET_CLOSE = time(15, 30)


class ExpirySettlementPolicy:
    def is_expired(self, option: ParsedOptionSymbol, now: datetime) -> bool:
        local = now.astimezone(IST)
        return option.expiry < local.date() or (option.expiry == local.date() and local.time() >= MARKET_CLOSE)

    def settlement_price(self, option: ParsedOptionSymbol, spot: float) -> float:
        intrinsic = spot - option.strike if option.option_type == OptionType.CE else option.strike - spot
        return round(max(0.0, intrinsic), 2)
