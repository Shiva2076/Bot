from datetime import date

from schemas.options import OptionType, OptionUnderlying
from services.options.option_symbol_parser import OptionSymbolParser


def test_parses_nifty_style_symbol():
    parsed = OptionSymbolParser().parse("NIFTY09NOV2620050CE")
    assert parsed is not None
    assert parsed.underlying == OptionUnderlying.NIFTY
    assert parsed.expiry == date(2026, 11, 9)
    assert parsed.strike == 20050.0
    assert parsed.option_type == OptionType.CE


def test_parses_sensex_weekly_symbol():
    parsed = OptionSymbolParser().parse("SENSEX26O2269800PE")
    assert parsed is not None
    assert parsed.underlying == OptionUnderlying.SENSEX
    assert parsed.expiry == date(2026, 10, 22)
    assert parsed.strike == 69800.0
    assert parsed.option_type == OptionType.PE


def test_rejects_sensex_monthly_without_day():
    # Monthlies need Angel scrip expiry via OptionContractResolver.
    assert OptionSymbolParser().parse("SENSEX26NOV72400PE") is None
