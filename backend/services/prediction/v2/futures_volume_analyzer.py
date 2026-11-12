from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

import pytz

from schemas.prediction import FactorCluster, PredictionFactor
from schemas.trading import Candle
from services.prediction.factor_builder import PredictionFactorBuilder

IST = pytz.timezone("Asia/Kolkata")
BAR_MINUTES = 5
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)   # bars starting at/after 15:30 are post-close prints, excluded
FUTURES_VWAP_NAME = "VWAP (futures 5m)"
FUTURES_RVOL_NAME = "Relative Volume (futures 5m)"

Bar = Tuple[datetime, Candle]


class FuturesVolumeAnalyzer:
    """v2 VWAP and RVOL rebuilt from near-month futures volume (the index feed has none).

    Completeness first: today's completed regular-session 5m bars must start at 09:15, be
    contiguous and all carry volume > 0, otherwise both factors are unavailable.
    RVOL compares the last completed bar with the same time-of-day bar of prior sessions and
    only confirms the bar's own direction when volume is above that average.
    """

    def __init__(
        self,
        builder: PredictionFactorBuilder,
        vwap_weight: float,
        rvol_weight: float,
        min_session_bars: int,
        atr_period: int,
        rvol_lookback_sessions: int,
        rvol_min_prior_sessions: int,
    ):
        self._builder = builder
        self._vwap_weight = vwap_weight
        self._rvol_weight = rvol_weight
        self._min_bars = min_session_bars
        self._atr_period = atr_period
        self._rvol_lookback = rvol_lookback_sessions
        self._rvol_min_prior = rvol_min_prior_sessions

    def analyze(self, candles: Optional[List[Candle]], now: datetime, symbol: Optional[str]) -> List[PredictionFactor]:
        if not candles:
            reason = "Futures candles unavailable" + (f" for {symbol}" if symbol else "")
            return [self._unavailable(FUTURES_VWAP_NAME, reason), self._unavailable(FUTURES_RVOL_NAME, reason)]
        bars = self._completed_session_bars(candles, now)
        local_now = now.astimezone(IST)
        today = [b for b in bars if b[0].date() == local_now.date()]
        problem = self.completeness_problem(today)
        if problem is not None:
            return [self._unavailable(FUTURES_VWAP_NAME, problem), self._unavailable(FUTURES_RVOL_NAME, problem)]
        return [self._vwap(today, bars, symbol), self._rvol(today, bars, symbol)]

    # ── completeness ──────────────────────────────────────────────────────────

    def completeness_problem(self, today: List[Bar]) -> Optional[str]:
        if len(today) < self._min_bars:
            return f"Only {len(today)} completed futures bars today (need {self._min_bars})"
        if today[0][0].time() != SESSION_OPEN:
            return f"First futures bar today starts {today[0][0]:%H:%M}, not 09:15"
        for (prev, _), (cur, _) in zip(today, today[1:]):
            if cur - prev != timedelta(minutes=BAR_MINUTES):
                return f"Gap in futures bars between {prev:%H:%M} and {cur:%H:%M}"
        zero = [t for t, c in today if c.volume <= 0]
        if zero:
            return f"{len(zero)} futures bar(s) today with zero volume (first {zero[0]:%H:%M})"
        return None

    # ── factors ───────────────────────────────────────────────────────────────

    def _vwap(self, today: List[Bar], bars: List[Bar], symbol: Optional[str]) -> PredictionFactor:
        volume = sum(c.volume for _, c in today)
        vwap = sum((c.high + c.low + c.close) / 3.0 * c.volume for _, c in today) / volume
        atr = self._atr(bars)
        if atr is None or atr <= 0:
            return self._unavailable(FUTURES_VWAP_NAME, "Not enough futures bars for ATR")
        last = today[-1][1]
        score = (last.close - vwap) / atr
        side = "above" if last.close >= vwap else "below"
        return self._builder.build(
            name=FUTURES_VWAP_NAME,
            score=score,
            weight=self._vwap_weight,
            detail=(
                f"{symbol or 'Futures'} {last.close:.2f} is {side} session VWAP {vwap:.2f} "
                f"({score:+.2f} ATR, ATR {atr:.2f}, {len(today)} bars)"
            ),
            cluster=FactorCluster.LEVELS,
        )

    def _rvol(self, today: List[Bar], bars: List[Bar], symbol: Optional[str]) -> PredictionFactor:
        last_at, last = today[-1]
        # Only regular sessions (they open at 09:15); special sessions such as Muhurat are skipped.
        regular_days = {at.date() for at, _ in bars if at.time() == SESSION_OPEN}
        same_time: Dict = {}
        for at, candle in bars:
            if at.date() < last_at.date() and at.date() in regular_days and at.time() == last_at.time():
                same_time[at.date()] = candle.volume
        prior = [same_time[d] for d in sorted(same_time)][-self._rvol_lookback:]
        if len(prior) < self._rvol_min_prior:
            return self._unavailable(
                FUTURES_RVOL_NAME,
                f"{len(prior)} prior sessions with a {last_at:%H:%M} bar (need {self._rvol_min_prior})",
            )
        average = sum(prior) / len(prior)
        rvol = last.volume / average if average > 0 else 0.0
        direction = 1.0 if last.close > last.open else (-1.0 if last.close < last.open else 0.0)
        detail = (
            f"{last_at:%H:%M} bar volume {last.volume:.0f} vs {len(prior)}-session same-time average "
            f"{average:.0f}: RVOL {rvol:.2f}x; bar {'up' if direction > 0 else 'down' if direction < 0 else 'flat'}"
        )
        if direction == 0 or rvol <= 1.0:
            return self._builder.neutral(
                name=FUTURES_RVOL_NAME, detail=f"{detail}; no volume confirmation", cluster=FactorCluster.LEVELS
            )
        return self._builder.build(
            name=FUTURES_RVOL_NAME,
            score=direction * min(1.0, rvol - 1.0),
            weight=self._rvol_weight,
            detail=detail,
            cluster=FactorCluster.LEVELS,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _atr(self, bars: List[Bar]) -> Optional[float]:
        window = bars[-(self._atr_period + 1):]
        if len(window) < self._atr_period + 1:
            return None
        ranges = [
            max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
            for (_, prev), (_, c) in zip(window, window[1:])
        ]
        return sum(ranges) / len(ranges)

    @staticmethod
    def _completed_session_bars(candles: List[Candle], now: datetime) -> List[Bar]:
        bars: List[Bar] = []
        for candle in candles:
            start = datetime.fromtimestamp(candle.time, IST)
            if not (SESSION_OPEN <= start.time() < SESSION_CLOSE):
                continue
            if start + timedelta(minutes=BAR_MINUTES) > now:
                continue
            bars.append((start, candle))
        bars.sort(key=lambda b: b[0])
        return bars

    def _unavailable(self, name: str, detail: str) -> PredictionFactor:
        return self._builder.unavailable(name=name, detail=detail, cluster=FactorCluster.LEVELS)
