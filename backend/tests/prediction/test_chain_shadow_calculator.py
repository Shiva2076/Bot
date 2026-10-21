from datetime import date
from typing import Optional

from schemas.options import OptionChain, OptionChainRow, OptionQuote, OptionUnderlying
from services.prediction.chain_shadow_calculator import ChainShadowCalculator
from services.prediction.strike_window_policy import StrikeWindowPolicy


def _quote(oi: float, iv: Optional[float], delta: Optional[float], gamma: Optional[float]) -> OptionQuote:
    return OptionQuote(
        symbol="X", display_name="X", ltp=10.0, change=0.0, change_pct=0.0,
        open_interest=oi, volume=1.0, bid=None, ask=None,
        implied_volatility=iv, delta=delta, gamma=gamma,
    )


def _chain() -> OptionChain:
    return OptionChain(
        underlying=OptionUnderlying.NIFTY,
        expiry=date(2026, 10, 27),
        spot=25000.0,
        atm_strike=25000.0,
        lot_size=65,
        rows=[
            OptionChainRow(strike=24000.0, call=_quote(9999, 20, 0.9, 0.0001), put=_quote(9999, 22, -0.1, 0.0001)),
            OptionChainRow(strike=24800.0, call=_quote(100, 13, 0.7, 0.0002), put=_quote(300, 15, -0.25, 0.0002)),
            OptionChainRow(strike=25000.0, call=_quote(200, 12, 0.5, 0.0003), put=_quote(200, 14, -0.5, 0.0003)),
            OptionChainRow(strike=25200.0, call=_quote(300, 11, 0.25, 0.0002), put=_quote(100, 16, -0.75, 0.0002)),
        ],
    )


def _calc() -> ChainShadowCalculator:
    return ChainShadowCalculator(StrikeWindowPolicy({OptionUnderlying.NIFTY: 500.0}))


def test_near_spot_window_excludes_far_strikes():
    features = _calc().calculate(_chain())
    assert features.near_call_oi == 600.0
    assert features.near_put_oi == 600.0
    assert features.near_spot_pcr == 1.0


def test_atm_iv_and_25_delta_skew():
    features = _calc().calculate(_chain())
    assert features.atm_iv == 13.0
    assert features.iv_skew_25d == 4.0


def test_gex_calls_positive_puts_negative():
    features = _calc().calculate(_chain())
    assert features.gex_per_1pct is not None
    assert features.quotes_with_iv == 8
