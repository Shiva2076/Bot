from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from schemas.prediction import StructureBias
from schemas.trading import Candle
from services.prediction.chart_swing_detector import SwingKind, SwingPoint


class StructureEventKind(str, Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"


class StructureEvent(BaseModel):
    kind: StructureEventKind
    bias: StructureBias
    level: float
    index: int
    time: int
    evidence: str


class ChartStructureEventDetector:
    """
    BOS: continuation break of the latest opposing swing in the prevailing structure.
    CHoCH: first opposite break that flips the prior bullish/bearish structure.
    Uses only confirmed swings (no lookahead beyond swing confirmation).
    """

    def detect(
        self,
        candles: List[Candle],
        swings: List[SwingPoint],
        structure: StructureBias,
        atr: float,
    ) -> Optional[StructureEvent]:
        if atr <= 0 or len(candles) < 5:
            return None
        highs = [s for s in swings if s.kind == SwingKind.HIGH]
        lows = [s for s in swings if s.kind == SwingKind.LOW]
        if not highs or not lows:
            return None
        last_high = highs[-1]
        last_low = lows[-1]
        epsilon = atr * 0.05
        # Scan closes after both swings are confirmed
        start = max(last_high.confirmed_at_index, last_low.confirmed_at_index) + 1
        for index in range(start, len(candles)):
            close = candles[index].close
            if structure == StructureBias.BULLISH and close < last_low.price - epsilon:
                return StructureEvent(
                    kind=StructureEventKind.CHOCH,
                    bias=StructureBias.BEARISH,
                    level=last_low.price,
                    index=index,
                    time=candles[index].time,
                    evidence=f"CHoCH: close below last higher-low {last_low.price:.2f}",
                )
            if structure == StructureBias.BEARISH and close > last_high.price + epsilon:
                return StructureEvent(
                    kind=StructureEventKind.CHOCH,
                    bias=StructureBias.BULLISH,
                    level=last_high.price,
                    index=index,
                    time=candles[index].time,
                    evidence=f"CHoCH: close above last lower-high {last_high.price:.2f}",
                )
            if structure == StructureBias.BULLISH and close > last_high.price + epsilon:
                return StructureEvent(
                    kind=StructureEventKind.BOS,
                    bias=StructureBias.BULLISH,
                    level=last_high.price,
                    index=index,
                    time=candles[index].time,
                    evidence=f"BOS: close above last swing high {last_high.price:.2f}",
                )
            if structure == StructureBias.BEARISH and close < last_low.price - epsilon:
                return StructureEvent(
                    kind=StructureEventKind.BOS,
                    bias=StructureBias.BEARISH,
                    level=last_low.price,
                    index=index,
                    time=candles[index].time,
                    evidence=f"BOS: close below last swing low {last_low.price:.2f}",
                )
        return None
