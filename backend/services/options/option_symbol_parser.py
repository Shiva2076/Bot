import re
from datetime import datetime
from typing import Optional

from schemas.options import OptionType, OptionUnderlying, ParsedOptionSymbol

OPTION_SYMBOL_PATTERN = re.compile(
    r"^(?P<underlying>[A-Z]+?)(?P<expiry>\d{2}[A-Z]{3}\d{2})(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE)$"
)


class OptionSymbolParser:
    def parse(self, symbol: str) -> Optional[ParsedOptionSymbol]:
        match = OPTION_SYMBOL_PATTERN.match(symbol)
        if match is None or match.group("underlying") not in OptionUnderlying.__members__:
            return None
        return ParsedOptionSymbol(
            underlying=OptionUnderlying(match.group("underlying")),
            expiry=datetime.strptime(match.group("expiry"), "%d%b%y").date(),
            strike=float(match.group("strike")),
            option_type=OptionType(match.group("type")),
        )

    def display_name(self, parsed: ParsedOptionSymbol) -> str:
        strike = int(parsed.strike) if parsed.strike.is_integer() else parsed.strike
        return f"{parsed.underlying.value} {parsed.expiry.strftime('%d %b').upper()} {strike} {parsed.option_type.value}"
