"""
Time Context Analyzer — encodes time-of-day and expiry-day effects as a
confidence modifier and a session label for the prediction pipeline.

Key behaviours modelled:
  • Opening (9:15–9:45): High volatility, gap-fill behaviour, low follow-through.
    → Suppress direction confidence; only very strong signals should be acted on.
  • Mid-morning (9:45–11:30): Best trend-following window of the day.
    → Full confidence.
  • Midday lull (11:30–13:00): Thin liquidity, mean-reversion, false breakouts.
    → Mild suppression.
  • Afternoon trend (13:00–14:30): Often resumes morning trend or sets up close.
    → Good window, slight boost if trend is strong.
  • Pre-close / close (14:30–15:30): Gamma/theta unwinding, position squaring.
    → Suppress on non-expiry days; on expiry days be very cautious.
  • Expiry day (the selected contract's expiry date):
    → Gamma exposure is at maximum; pin-risk near ATM; OI-based factors matter more.
"""
from datetime import date, datetime, time as dtime
from typing import Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")

# Session windows (IST)
_OPENING_START = dtime(9, 15)
_OPENING_END = dtime(9, 45)
_MID_MORNING_END = dtime(11, 30)
_LULL_END = dtime(13, 0)
_AFTERNOON_END = dtime(14, 30)
_CLOSE_END = dtime(15, 30)


class TimeContext:
    __slots__ = ("session", "is_expiry_day", "confidence_modifier", "detail")

    def __init__(
        self,
        session: str,
        is_expiry_day: bool,
        confidence_modifier: float,
        detail: str,
    ):
        self.session = session
        self.is_expiry_day = is_expiry_day
        self.confidence_modifier = confidence_modifier
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"TimeContext(session={self.session!r}, expiry={self.is_expiry_day}, "
            f"modifier={self.confidence_modifier:.2f})"
        )


class TimeContextAnalyzer:
    """
    Stateless analyzer — call `analyze()` at prediction time.
    """

    def analyze(self, expiry_date: date, now: Optional[datetime] = None) -> TimeContext:
        if now is None:
            now = datetime.now(IST)
        elif now.tzinfo is None:
            now = IST.localize(now)
        else:
            now = now.astimezone(IST)

        t = now.time()
        expiry = now.date() == expiry_date

        session, modifier = self._session_and_modifier(t, expiry)

        detail_parts = [f"Session: {session}"]
        if expiry:
            detail_parts.append("⚠ Expiry day — gamma at max, pin-risk elevated")
        detail_parts.append(f"Confidence modifier: {modifier:.0%}")
        detail = "; ".join(detail_parts)

        return TimeContext(
            session=session,
            is_expiry_day=expiry,
            confidence_modifier=modifier,
            detail=detail,
        )

    @staticmethod
    def _session_and_modifier(t: dtime, is_expiry: bool):
        """Map current time → (session_label, confidence_modifier)."""
        if t < _OPENING_START or t >= _CLOSE_END:
            return "PRE_CLOSE_OR_CLOSED", 0.70

        if t < _OPENING_END:
            # Opening: high noise, gap-fill behaviour
            modifier = 0.65 if not is_expiry else 0.55
            return "OPENING", modifier

        if t < _MID_MORNING_END:
            # Best trend-following window
            modifier = 1.0 if not is_expiry else 0.90
            return "MID_MORNING", modifier

        if t < _LULL_END:
            # Midday lull: thin liquidity, chop risk
            modifier = 0.80 if not is_expiry else 0.75
            return "MIDDAY_LULL", modifier

        if t < _AFTERNOON_END:
            # Afternoon: often resumes or reverses morning trend
            modifier = 0.90 if not is_expiry else 0.80
            return "AFTERNOON", modifier

        # Pre-close: gamma unwind, position squaring
        modifier = 0.70 if not is_expiry else 0.50
        return "PRE_CLOSE", modifier
