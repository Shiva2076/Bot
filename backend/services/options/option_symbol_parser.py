import re
from datetime import date, datetime
from typing import Dict, Optional

from schemas.options import OptionType, OptionUnderlying, ParsedOptionSymbol

# NIFTY / BANKNIFTY: NIFTY09NOV2620050CE
OPTION_SYMBOL_PATTERN = re.compile(
    r"^(?P<underlying>[A-Z]+?)(?P<expiry>\d{2}[A-Z]{3}\d{2})(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE)$"
)
# Sensex weekly BFO: SENSEX26O2269800PE (YY + month code + DD + strike)
SENSEX_WEEKLY_PATTERN = re.compile(
    r"^SENSEX(?P<year>\d{2})(?P<month>[1-9OND])(?P<day>\d{2})(?P<strike>\d+)(?P<type>CE|PE)$"
)
WEEKLY_MONTH_CODES: Dict[str, int] = {
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "O": 10, "N": 11, "D": 12,
}


class OptionSymbolParser:
    def parse(self, symbol: str) -> Optional[ParsedOptionSymbol]:
        # Sensex monthlies use YYMMM+strike (no day) and must not use the NSE DDMMMYY pattern.
        weekly = SENSEX_WEEKLY_PATTERN.match(symbol)
        if weekly is not None:
            month = WEEKLY_MONTH_CODES[weekly.group("month")]
            year = 2000 + int(weekly.group("year"))
            day = int(weekly.group("day"))
            return ParsedOptionSymbol(
                underlying=OptionUnderlying.SENSEX,
                expiry=date(year, month, day),
                strike=float(weekly.group("strike")),
                option_type=OptionType(weekly.group("type")),
            )
        match = OPTION_SYMBOL_PATTERN.match(symbol)
        if match is None:
            return None
        underlying_name = match.group("underlying")
        if underlying_name not in OptionUnderlying.__members__:
            return None
        if underlying_name == OptionUnderlying.SENSEX.value:
            return None
        return ParsedOptionSymbol(
            underlying=OptionUnderlying(underlying_name),
            expiry=datetime.strptime(match.group("expiry"), "%d%b%y").date(),
            strike=float(match.group("strike")),
            option_type=OptionType(match.group("type")),
        )

    def display_name(self, parsed: ParsedOptionSymbol) -> str:
        strike = int(parsed.strike) if parsed.strike.is_integer() else parsed.strike
        return f"{parsed.underlying.value} {parsed.expiry.strftime('%d %b').upper()} {strike} {parsed.option_type.value}"
