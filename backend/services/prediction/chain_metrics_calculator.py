"""
ChainMetricsCalculator — computes summary metrics from the live option chain.

Now tracks OI across snapshots to derive delta-OI (long buildup / short covering /
unwinding) and extracts ATM IV for IV-rank downstream consumption.
"""
import time
from typing import Dict, List, Optional, Tuple

from schemas.options import OptionChain, OptionChainRow
from schemas.prediction import ChainMetrics
from services.prediction.strike_window_policy import StrikeWindowPolicy


# ── OI interpretation matrix ──────────────────────────────────────────────────
#
#  Price Δ    OI Δ    Interpretation
#  -------    ------  ------------------------------------------------
#  Up         Up      CALL_LONG_BUILDUP   — fresh longs entering
#  Up         Down    CALL_SHORT_COVERING — shorts exiting, weak rally
#  Down       Up      PUT_LONG_BUILDUP    — fresh shorts entering
#  Down       Down    PUT_SHORT_COVERING  — shorts exiting, weak bounce
#
# We use the net (call_oi_change - put_oi_change) direction as a proxy
# because intraday spot direction isn't available here.
# ─────────────────────────────────────────────────────────────────────────────

_OI_HISTORY_TTL = 300  # seconds — how long to keep a previous snapshot


class ChainMetricsCalculator:
    def __init__(self, windows: StrikeWindowPolicy) -> None:
        self._windows = windows
        # keyed by (underlying, expiry) → (timestamp, call_oi, put_oi)
        self._prev: Dict[str, Tuple[float, float, float]] = {}
        # rolling ATM IV history for IV-rank (last 20 readings)
        self._iv_history: Dict[str, List[float]] = {}

    def calculate(self, chain: OptionChain) -> ChainMetrics:
        total_call_oi = sum(self._call_oi(row) for row in chain.rows)
        total_put_oi = sum(self._put_oi(row) for row in chain.rows)
        atm_iv = self._atm_iv(chain)
        window = self._windows.window(chain.underlying)
        near = [row for row in chain.rows if abs(row.strike - chain.spot) <= window]
        near_call_oi = sum(self._call_oi(row) for row in near)
        near_put_oi = sum(self._put_oi(row) for row in near)

        # ── ΔOI dynamics ──────────────────────────────────────────────────────
        cache_key = f"{chain.underlying}:{chain.expiry}"
        call_oi_change, put_oi_change = self._oi_changes(
            cache_key, total_call_oi, total_put_oi
        )
        oi_interpretation = self._interpret_oi(call_oi_change, put_oi_change)

        # ── IV Rank ───────────────────────────────────────────────────────────
        iv_rank = None
        if atm_iv is not None:
            iv_rank = self._update_iv_rank(cache_key, atm_iv)

        return ChainMetrics(
            put_call_ratio=round(total_put_oi / total_call_oi, 2) if total_call_oi else 0.0,
            max_pain=self._max_pain(chain.rows),
            call_wall=max(chain.rows, key=self._call_oi).strike,
            put_wall=max(chain.rows, key=self._put_oi).strike,
            total_call_oi=total_call_oi,
            total_put_oi=total_put_oi,
            call_oi_change=round(call_oi_change, 0),
            put_oi_change=round(put_oi_change, 0),
            oi_interpretation=oi_interpretation,
            atm_iv=round(atm_iv, 2) if atm_iv is not None else None,
            iv_rank=round(iv_rank, 1) if iv_rank is not None else None,
            near_spot_pcr=round(near_put_oi / near_call_oi, 3) if near_call_oi > 0 else None,
            strike_window=window,
        )

    # ── OI delta helpers ──────────────────────────────────────────────────────

    def _oi_changes(
        self, key: str, call_oi: float, put_oi: float
    ) -> Tuple[float, float]:
        now = time.time()
        prev = self._prev.get(key)
        if prev and (now - prev[0]) < _OI_HISTORY_TTL:
            call_change = call_oi - prev[1]
            put_change = put_oi - prev[2]
        else:
            call_change = 0.0
            put_change = 0.0
        # Always update the snapshot
        self._prev[key] = (now, call_oi, put_oi)
        return call_change, put_change

    @staticmethod
    def _interpret_oi(call_change: float, put_change: float) -> str:
        """Classify the dominant OI shift into a human-readable label."""
        threshold = 500  # contracts — ignore noise below this
        if abs(call_change) < threshold and abs(put_change) < threshold:
            return "STABLE"
        if call_change > threshold and put_change < -threshold:
            return "CALL_BUILDUP_PUT_UNWINDING"   # strongly bullish
        if call_change > threshold:
            return "CALL_LONG_BUILDUP"             # bullish
        if put_change > threshold and call_change < -threshold:
            return "PUT_BUILDUP_CALL_UNWINDING"    # strongly bearish
        if put_change > threshold:
            return "PUT_LONG_BUILDUP"              # bearish
        if call_change < -threshold:
            return "CALL_SHORT_COVERING"           # weak bullish
        if put_change < -threshold:
            return "PUT_SHORT_COVERING"            # weak bearish
        return "MIXED"

    # ── IV helpers ────────────────────────────────────────────────────────────

    def _atm_iv(self, chain: OptionChain) -> Optional[float]:
        """Return ATM call IV as the best available IV proxy."""
        atm_row = next(
            (r for r in chain.rows if r.strike == chain.atm_strike), None
        )
        if atm_row is None:
            return None
        if atm_row.call and atm_row.call.implied_volatility:
            return atm_row.call.implied_volatility
        if atm_row.put and atm_row.put.implied_volatility:
            return atm_row.put.implied_volatility
        return None

    def _update_iv_rank(self, key: str, current_iv: float) -> float:
        """
        IV Rank = (current_iv - min_iv) / (max_iv - min_iv) * 100.
        Maintains a rolling window of up to 20 readings (≈ one trading day
        of 5-min snapshots).
        """
        history = self._iv_history.setdefault(key, [])
        history.append(current_iv)
        if len(history) > 20:
            history.pop(0)
        lo, hi = min(history), max(history)
        if hi == lo:
            return 50.0
        return (current_iv - lo) / (hi - lo) * 100.0

    # ── Max Pain ─────────────────────────────────────────────────────────────

    def _max_pain(self, rows: List[OptionChainRow]) -> float:
        return min(
            (row.strike for row in rows),
            key=lambda settle: sum(
                self._call_oi(r) * max(0.0, settle - r.strike)
                + self._put_oi(r) * max(0.0, r.strike - settle)
                for r in rows
            ),
        )

    @staticmethod
    def _call_oi(row: OptionChainRow) -> float:
        return row.call.open_interest if row.call else 0.0

    @staticmethod
    def _put_oi(row: OptionChainRow) -> float:
        return row.put.open_interest if row.put else 0.0
