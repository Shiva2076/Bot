from datetime import date, datetime

import pytest
import pytz

from schemas.options import OptionChain, OptionChainRow, OptionPricingInput, OptionQuote, OptionType, OptionUnderlying
from services.options.black_scholes_model import BlackScholesModel
from services.options.option_greeks_enricher import OptionGreeksEnricher

IST = pytz.timezone("Asia/Kolkata")


def _model() -> BlackScholesModel:
    return BlackScholesModel(min_vol=0.01, max_vol=3.0, iterations=100, tolerance=1e-4)


def _contract(option_type: OptionType) -> OptionPricingInput:
    return OptionPricingInput(option_type=option_type, spot=25000.0, strike=25000.0, years_to_expiry=7 / 365, rate=0.065)


@pytest.mark.parametrize("option_type", [OptionType.CE, OptionType.PE])
def test_implied_vol_round_trips(option_type: OptionType):
    model = _model()
    premium = model.price(_contract(option_type), 0.15)
    assert model.implied_vol(_contract(option_type), premium) == pytest.approx(0.15, abs=1e-3)


def test_greeks_signs():
    model = _model()
    call = model.greeks(_contract(OptionType.CE), 0.15)
    put = model.greeks(_contract(OptionType.PE), 0.15)
    assert 0 < call.delta < 1
    assert -1 < put.delta < 0
    assert call.gamma > 0 and call.vega > 0
    assert call.theta < 0
    assert call.implied_volatility == pytest.approx(15.0)


def test_premium_below_intrinsic_has_no_iv():
    contract = OptionPricingInput(
        option_type=OptionType.CE, spot=25500.0, strike=25000.0, years_to_expiry=7 / 365, rate=0.065
    )
    assert _model().implied_vol(contract, 400.0) is None


def _quote(ltp: float, bid: float, ask: float) -> OptionQuote:
    return OptionQuote(
        symbol="X", display_name="X", ltp=ltp, change=0.0, change_pct=0.0,
        open_interest=1000.0, volume=10.0, bid=bid, ask=ask,
    )


def test_enricher_fills_iv_and_greeks_from_mid():
    model = _model()
    expiry = date(2026, 10, 27)
    now = IST.localize(datetime(2026, 10, 20, 10, 0))
    enricher = OptionGreeksEnricher(model, 0.065)
    years = (IST.localize(datetime(2026, 10, 27, 15, 30)) - now).total_seconds() / (365 * 86400)
    fair = model.price(
        OptionPricingInput(option_type=OptionType.CE, spot=25000.0, strike=25000.0, years_to_expiry=years, rate=0.065),
        0.12,
    )
    chain = OptionChain(
        underlying=OptionUnderlying.NIFTY,
        expiry=expiry,
        spot=25000.0,
        atm_strike=25000.0,
        lot_size=65,
        rows=[OptionChainRow(strike=25000.0, call=_quote(fair + 5, fair - 1, fair + 1), put=None)],
    )
    call = enricher.enrich(chain, now).rows[0].call
    assert call.implied_volatility == pytest.approx(12.0, abs=0.2)
    assert call.delta is not None and call.gamma is not None
