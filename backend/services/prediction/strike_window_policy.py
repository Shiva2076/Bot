from typing import Dict

from schemas.options import OptionUnderlying


class StrikeWindowPolicy:
    def __init__(self, windows: Dict[OptionUnderlying, float]):
        self._windows = windows

    def window(self, underlying: OptionUnderlying) -> float:
        return self._windows[underlying]
