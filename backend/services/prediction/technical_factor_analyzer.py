from typing import List

from schemas.prediction import FactorCluster, IntradayIndicators, PredictionFactor, SessionRangeKind
from services.prediction.factor_builder import PredictionFactorBuilder

EMA_WEIGHT = 0.08
RSI_WEIGHT = 0.07
MACD_WEIGHT = 0.07
SUPERTREND_WEIGHT = 0.07
VWAP_WEIGHT = 0.10
RVOL_WEIGHT = 0.05
IB_WEIGHT = 0.06

RSI_FULL_SCALE = 20.0
MACD_FULL_SCALE_ATR = 0.05

SESSION_RANGE_LABELS = {
    SessionRangeKind.INITIAL_BALANCE: "IB",
    SessionRangeKind.OPENING_RANGE: "Opening range",
}


class TechnicalFactorAnalyzer:
    def __init__(self, builder: PredictionFactorBuilder, interval_label: str):
        self._builder = builder
        self._interval_label = interval_label

    def analyze(self, indicators: IntradayIndicators) -> List[PredictionFactor]:
        return [
            self._ema_trend(indicators),
            self._rsi(indicators),
            self._macd(indicators),
            self._supertrend(indicators),
            self._vwap(indicators),
            self._rvol(indicators),
            self._session_range(indicators),
        ]

    def _ema_trend(self, indicators: IntradayIndicators) -> PredictionFactor:
        side = "above" if indicators.price >= indicators.ema_20 else "below"
        return self._builder.build(
            name=f"EMA 20 Trend ({self._interval_label})",
            score=(indicators.price - indicators.ema_20) / indicators.atr,
            weight=EMA_WEIGHT,
            detail=f"Spot {indicators.price:.2f} is {side} EMA 20 at {indicators.ema_20:.2f}",
            cluster=FactorCluster.TREND,
        )

    def _rsi(self, indicators: IntradayIndicators) -> PredictionFactor:
        return self._builder.build(
            name=f"RSI ({self._interval_label})",
            score=(indicators.rsi - 50.0) / RSI_FULL_SCALE,
            weight=RSI_WEIGHT,
            detail=f"RSI {indicators.rsi:.1f}: above 50 bullish momentum, below 50 bearish",
            cluster=FactorCluster.LEVELS,
        )

    def _macd(self, indicators: IntradayIndicators) -> PredictionFactor:
        side = "positive" if indicators.macd_histogram >= 0 else "negative"
        return self._builder.build(
            name=f"MACD ({self._interval_label})",
            score=indicators.macd_histogram / (indicators.atr * MACD_FULL_SCALE_ATR),
            weight=MACD_WEIGHT,
            detail=f"MACD histogram {indicators.macd_histogram:.2f} is {side}",
            cluster=FactorCluster.TREND,
        )

    def _supertrend(self, indicators: IntradayIndicators) -> PredictionFactor:
        trend = "up" if indicators.supertrend_direction > 0 else "down"
        return self._builder.build(
            name=f"Supertrend ({self._interval_label})",
            score=float(indicators.supertrend_direction),
            weight=SUPERTREND_WEIGHT,
            detail=f"Supertrend is pointing {trend}",
            cluster=FactorCluster.TREND,
        )

    def _vwap(self, indicators: IntradayIndicators) -> PredictionFactor:
        name = f"VWAP ({self._interval_label})"
        if indicators.vwap is None or indicators.atr == 0:
            return self._builder.unavailable(
                name=name,
                detail="VWAP needs traded volume; the index spot feed reports none",
                cluster=FactorCluster.LEVELS,
            )
        score = (indicators.price - indicators.vwap) / indicators.atr
        side = "above" if indicators.price >= indicators.vwap else "below"
        return self._builder.build(
            name=name,
            score=score,
            weight=VWAP_WEIGHT,
            detail=f"Spot {indicators.price:.2f} is {side} VWAP at {indicators.vwap:.2f} ({score:+.2f} ATRs)",
            cluster=FactorCluster.LEVELS,
        )

    def _rvol(self, indicators: IntradayIndicators) -> PredictionFactor:
        name = f"Relative Volume ({self._interval_label})"
        rvol = indicators.rvol if indicators.rvol is not None else indicators.volume_ratio
        if rvol is None:
            return self._builder.unavailable(
                name=name,
                detail="Relative volume needs traded volume; the index spot feed reports none",
                cluster=FactorCluster.LEVELS,
            )
        label = "high" if rvol >= 1.5 else ("low" if rvol < 0.7 else "average")
        return self._builder.build(
            name=name,
            score=rvol - 1.0,
            weight=RVOL_WEIGHT,
            detail=f"RVOL {rvol:.2f}x — {label} participation (>1.5 confirms breakouts)",
            cluster=FactorCluster.LEVELS,
        )

    def _session_range(self, indicators: IntradayIndicators) -> PredictionFactor:
        name = f"Initial Balance ({self._interval_label})"
        session_range = indicators.session_range
        if session_range is None or session_range.high <= session_range.low:
            return self._builder.unavailable(
                name=name,
                detail="Today's opening range has not formed yet",
                cluster=FactorCluster.LEVELS,
            )
        label = f"{SESSION_RANGE_LABELS[session_range.kind]} ({session_range.minutes}m)"
        width = session_range.high - session_range.low
        price = indicators.price
        if price > session_range.high:
            score = (price - session_range.high) / width
            detail = f"Price {price:.2f} above today's {label} high {session_range.high:.2f} — breakout"
        elif price < session_range.low:
            score = (price - session_range.low) / width
            detail = f"Price {price:.2f} below today's {label} low {session_range.low:.2f} — breakdown"
        else:
            mid = (session_range.high + session_range.low) / 2
            score = (price - mid) / (width / 2) * 0.5
            detail = f"Price {price:.2f} inside today's {label} [{session_range.low:.2f}–{session_range.high:.2f}]"
        return self._builder.build(
            name=name, score=score, weight=IB_WEIGHT, detail=detail, cluster=FactorCluster.LEVELS
        )
