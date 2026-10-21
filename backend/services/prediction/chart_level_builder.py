from typing import List, Optional

from schemas.prediction import ChartLevel, ChartLevelKind, SessionRange
from services.prediction.chart_prior_day_levels import PriorDayLevels
from services.prediction.chart_swing_detector import SwingKind, SwingPoint


class ChartLevelBuilder:
    def build(
        self,
        prior_day: Optional[PriorDayLevels],
        session_range: Optional[SessionRange],
        swings: List[SwingPoint],
        opening_gap_points: Optional[float],
        today_open: Optional[float],
    ) -> List[ChartLevel]:
        levels: List[ChartLevel] = []
        if prior_day is not None:
            source = f"daily:{prior_day.session_date.isoformat()}"
            levels.extend(
                [
                    ChartLevel(kind=ChartLevelKind.PDH, price=prior_day.pdh, source=source),
                    ChartLevel(kind=ChartLevelKind.PDL, price=prior_day.pdl, source=source),
                    ChartLevel(kind=ChartLevelKind.PDC, price=prior_day.pdc, source=source),
                ]
            )
        if opening_gap_points is not None and today_open is not None and prior_day is not None:
            levels.append(
                ChartLevel(
                    kind=ChartLevelKind.OPENING_GAP,
                    price=today_open,
                    source=f"gap_vs_pdc:{opening_gap_points:+.2f}",
                )
            )
        if session_range is not None:
            label = session_range.kind.value
            levels.append(
                ChartLevel(
                    kind=ChartLevelKind.SESSION_HIGH,
                    price=session_range.high,
                    source=f"{label}:{session_range.minutes}m",
                )
            )
            levels.append(
                ChartLevel(
                    kind=ChartLevelKind.SESSION_LOW,
                    price=session_range.low,
                    source=f"{label}:{session_range.minutes}m",
                )
            )
        highs = [s for s in swings if s.kind == SwingKind.HIGH][-2:]
        lows = [s for s in swings if s.kind == SwingKind.LOW][-2:]
        for swing in highs:
            levels.append(
                ChartLevel(kind=ChartLevelKind.SWING_HIGH, price=swing.price, source=f"pivot:{swing.index}")
            )
        for swing in lows:
            levels.append(
                ChartLevel(kind=ChartLevelKind.SWING_LOW, price=swing.price, source=f"pivot:{swing.index}")
            )
        return levels
