from typing import List, Optional, Tuple

from schemas.options import OptionChain, OptionChainRow, OptionQuote, OptionType

OTM_STEPS = 2


class StrikeSelector:
    def select(self, chain: OptionChain, option_type: OptionType) -> Optional[Tuple[float, OptionQuote]]:
        candidates = [
            (row.strike, leg)
            for row in self._near_atm(chain, option_type)
            for leg in [row.call if option_type == OptionType.CE else row.put]
            if leg and leg.ltp > 0
        ]
        return max(candidates, key=lambda candidate: candidate[1].volume, default=None)

    @staticmethod
    def _near_atm(chain: OptionChain, option_type: OptionType) -> List[OptionChainRow]:
        atm_index = next(i for i, row in enumerate(chain.rows) if row.strike == chain.atm_strike)
        if option_type == OptionType.CE:
            return chain.rows[atm_index:atm_index + OTM_STEPS + 1]
        return chain.rows[max(0, atm_index - OTM_STEPS):atm_index + 1]
