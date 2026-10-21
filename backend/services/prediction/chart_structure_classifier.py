from typing import List

from schemas.prediction import StructureBias
from services.prediction.chart_swing_detector import SwingKind, SwingPoint


class ChartStructureClassifier:
    def classify(self, swings: List[SwingPoint]) -> StructureBias:
        highs = [s for s in swings if s.kind == SwingKind.HIGH]
        lows = [s for s in swings if s.kind == SwingKind.LOW]
        if len(highs) < 2 or len(lows) < 2:
            return StructureBias.RANGE
        last_highs = highs[-2:]
        last_lows = lows[-2:]
        higher_highs = last_highs[1].price > last_highs[0].price
        higher_lows = last_lows[1].price > last_lows[0].price
        lower_highs = last_highs[1].price < last_highs[0].price
        lower_lows = last_lows[1].price < last_lows[0].price
        if higher_highs and higher_lows:
            return StructureBias.BULLISH
        if lower_highs and lower_lows:
            return StructureBias.BEARISH
        return StructureBias.RANGE
