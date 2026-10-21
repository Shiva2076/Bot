from datetime import datetime, timedelta

import pytz

from schemas.prediction import ChartPatternStatus, ChartProjectionKind
from schemas.trading import Candle
from services.prediction.chart_breakout_detector import BreakoutKind, BreakoutResult
from services.prediction.chart_double_pattern_detector import DoublePatternKind, DoublePatternResult
from services.prediction.chart_projection_builder import ChartProjectionBuilder
from services.prediction.chart_trendline_detector import ParallelChannel, TrendlineSegment

IST = pytz.timezone("Asia/Kolkata")


def _candle(ts: datetime, close: float) -> Candle:
    return Candle(
        time=int(ts.timestamp()),
        open=close,
        high=close + 5,
        low=close - 5,
        close=close,
        volume=1.0,
    )


def test_double_bottom_measured_move_projects_forward():
    start = IST.localize(datetime(2026, 10, 20, 10, 0))
    last = _candle(start, 25050.0)
    pattern = DoublePatternResult(
        kind=DoublePatternKind.DOUBLE_BOTTOM,
        status=ChartPatternStatus.CONFIRMED,
        bias=__import__("schemas.prediction", fromlist=["StructureBias"]).StructureBias.BULLISH,
        peak_or_trough=24900.0,
        neckline=25000.0,
        invalidation=24880.0,
        evidence="double bottom",
        time=int(start.timestamp()),
    )
    projections = ChartProjectionBuilder().build(
        candles=[last],
        atr=40.0,
        channel=None,
        double_pattern=pattern,
        breakout=BreakoutResult(
            kind=BreakoutKind.NONE, level=0.0, level_label="", break_index=None, evidence=""
        ),
    )
    kinds = {p.kind for p in projections}
    assert ChartProjectionKind.MEASURED_MOVE in kinds
    assert ChartProjectionKind.TARGET_ZONE in kinds
    move = next(p for p in projections if p.kind == ChartProjectionKind.MEASURED_MOVE)
    assert move.price_end == 25100.0  # neckline + height
    assert move.time_end > move.time_start
    assert move.side == "BULLISH"


def test_channel_extends_beyond_last_bar():
    start = IST.localize(datetime(2026, 10, 20, 9, 15))
    end = start + timedelta(minutes=50)
    last = _candle(end, 25020.0)
    upper = TrendlineSegment(
        kind="RESISTANCE_TRENDLINE",
        price_start=25010.0,
        price_end=25040.0,
        time_start=int(start.timestamp()),
        time_end=int(end.timestamp()),
        slope_per_bar=3.0,
        source="t",
    )
    lower = TrendlineSegment(
        kind="SUPPORT_TRENDLINE",
        price_start=24980.0,
        price_end=25000.0,
        time_start=int(start.timestamp()),
        time_end=int(end.timestamp()),
        slope_per_bar=2.0,
        source="t",
    )
    channel = ParallelChannel(upper=upper, lower=lower, width=40.0, evidence="channel")
    projections = ChartProjectionBuilder().build(
        candles=[last],
        atr=30.0,
        channel=channel,
        double_pattern=None,
        breakout=BreakoutResult(
            kind=BreakoutKind.NONE, level=0.0, level_label="", break_index=None, evidence=""
        ),
    )
    assert any(p.kind == ChartProjectionKind.CHANNEL_UPPER for p in projections)
    upper_proj = next(p for p in projections if p.kind == ChartProjectionKind.CHANNEL_UPPER)
    assert upper_proj.time_end > last.time
    assert upper_proj.price_end > upper.price_end
