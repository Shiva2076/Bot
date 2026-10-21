from typing import List, Optional

from schemas.options import OptionChain, OptionChainRow, OptionQuote
from schemas.prediction import ChainShadowFeatures
from services.prediction.strike_window_policy import StrikeWindowPolicy

SKEW_DELTA = 0.25
GEX_MOVE_PCT = 0.01


class ChainShadowCalculator:
    """Shadow-only chain features: logged for study, never scored."""

    def __init__(self, windows: StrikeWindowPolicy):
        self._windows = windows

    def near_rows(self, chain: OptionChain) -> List[OptionChainRow]:
        window = self._windows.window(chain.underlying)
        return [row for row in chain.rows if abs(row.strike - chain.spot) <= window]

    def calculate(self, chain: OptionChain) -> ChainShadowFeatures:
        near = self.near_rows(chain)
        calls = [row.call for row in chain.rows if row.call is not None]
        puts = [row.put for row in chain.rows if row.put is not None]
        near_call_oi = sum(row.call.open_interest for row in near if row.call is not None)
        near_put_oi = sum(row.put.open_interest for row in near if row.put is not None)
        return ChainShadowFeatures(
            strike_window=self._windows.window(chain.underlying),
            near_call_oi=near_call_oi,
            near_put_oi=near_put_oi,
            near_spot_pcr=round(near_put_oi / near_call_oi, 3) if near_call_oi > 0 else None,
            atm_iv=self.atm_iv(chain),
            iv_skew_25d=self._skew(calls, puts),
            gex_per_1pct=self._gex(chain.spot, calls, puts),
            quotes_with_iv=sum(1 for q in calls + puts if q.implied_volatility is not None),
            quotes_total=len(calls) + len(puts),
        )

    @staticmethod
    def atm_iv(chain: OptionChain) -> Optional[float]:
        atm = next((row for row in chain.rows if row.strike == chain.atm_strike), None)
        if atm is None:
            return None
        ivs = [q.implied_volatility for q in (atm.call, atm.put) if q is not None and q.implied_volatility is not None]
        return round(sum(ivs) / len(ivs), 2) if ivs else None

    @staticmethod
    def _skew(calls: List[OptionQuote], puts: List[OptionQuote]) -> Optional[float]:
        call = ChainShadowCalculator._closest_delta(calls, SKEW_DELTA)
        put = ChainShadowCalculator._closest_delta(puts, -SKEW_DELTA)
        if call is None or put is None:
            return None
        return round(put.implied_volatility - call.implied_volatility, 2)

    @staticmethod
    def _closest_delta(quotes: List[OptionQuote], target: float) -> Optional[OptionQuote]:
        priced = [q for q in quotes if q.delta is not None and q.implied_volatility is not None]
        return min(priced, key=lambda q: abs(q.delta - target), default=None)

    @staticmethod
    def _gex(spot: float, calls: List[OptionQuote], puts: List[OptionQuote]) -> Optional[float]:
        scale = spot * spot * GEX_MOVE_PCT
        call_gex = [q.gamma * q.open_interest * scale for q in calls if q.gamma is not None]
        put_gex = [q.gamma * q.open_interest * scale for q in puts if q.gamma is not None]
        if not call_gex and not put_gex:
            return None
        return round(sum(call_gex) - sum(put_gex), 0)
