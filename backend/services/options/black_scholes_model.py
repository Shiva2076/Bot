import math
from typing import Optional

from schemas.options import OptionGreeks, OptionPricingInput, OptionType

DAYS_PER_YEAR = 365.0


class BlackScholesModel:
    """European Black-Scholes on spot with a flat risk-free rate and no dividend yield."""

    def __init__(self, min_vol: float, max_vol: float, iterations: int, tolerance: float):
        self._min_vol = min_vol
        self._max_vol = max_vol
        self._iterations = iterations
        self._tolerance = tolerance

    def price(self, contract: OptionPricingInput, vol: float) -> float:
        d1, d2 = self._d1_d2(contract, vol)
        discount = math.exp(-contract.rate * contract.years_to_expiry)
        if contract.option_type == OptionType.CE:
            return contract.spot * self._cdf(d1) - contract.strike * discount * self._cdf(d2)
        return contract.strike * discount * self._cdf(-d2) - contract.spot * self._cdf(-d1)

    def implied_vol(self, contract: OptionPricingInput, premium: float) -> Optional[float]:
        if premium <= self._intrinsic(contract) + self._tolerance:
            return None
        low, high = self._min_vol, self._max_vol
        if self.price(contract, high) < premium or self.price(contract, low) > premium:
            return None
        for _ in range(self._iterations):
            mid = (low + high) / 2.0
            if self.price(contract, mid) < premium:
                low = mid
            else:
                high = mid
            if high - low < self._tolerance:
                break
        return (low + high) / 2.0

    def greeks(self, contract: OptionPricingInput, vol: float) -> OptionGreeks:
        d1, d2 = self._d1_d2(contract, vol)
        sqrt_t = math.sqrt(contract.years_to_expiry)
        discount = math.exp(-contract.rate * contract.years_to_expiry)
        pdf_d1 = self._pdf(d1)
        decay = -contract.spot * pdf_d1 * vol / (2.0 * sqrt_t)
        if contract.option_type == OptionType.CE:
            delta = self._cdf(d1)
            theta_annual = decay - contract.rate * contract.strike * discount * self._cdf(d2)
        else:
            delta = self._cdf(d1) - 1.0
            theta_annual = decay + contract.rate * contract.strike * discount * self._cdf(-d2)
        return OptionGreeks(
            implied_volatility=round(vol * 100.0, 2),
            delta=round(delta, 4),
            gamma=round(pdf_d1 / (contract.spot * vol * sqrt_t), 6),
            theta=round(theta_annual / DAYS_PER_YEAR, 4),
            vega=round(contract.spot * pdf_d1 * sqrt_t / 100.0, 4),
        )

    def _intrinsic(self, contract: OptionPricingInput) -> float:
        discounted_strike = contract.strike * math.exp(-contract.rate * contract.years_to_expiry)
        if contract.option_type == OptionType.CE:
            return max(0.0, contract.spot - discounted_strike)
        return max(0.0, discounted_strike - contract.spot)

    @staticmethod
    def _d1_d2(contract: OptionPricingInput, vol: float):
        sqrt_t = math.sqrt(contract.years_to_expiry)
        d1 = (
            math.log(contract.spot / contract.strike)
            + (contract.rate + 0.5 * vol * vol) * contract.years_to_expiry
        ) / (vol * sqrt_t)
        return d1, d1 - vol * sqrt_t

    @staticmethod
    def _cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @staticmethod
    def _pdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
