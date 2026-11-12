from datetime import date
from typing import List, Optional

from schemas.prediction import IvRankGate, IvRankGateStatus
from schemas.shadow_v2 import DailyAtmIv


class IvRankGateEvaluator:
    """v2 IV Rank: a gate on option buying, never a directional vote.

    Rank compares today's ATM IV with one stored reading per prior session. The gate stays
    OFF until `min_sessions` prior sessions exist; at or above `block_at` it blocks buying.
    """

    def __init__(self, lookback_sessions: int, min_sessions: int, block_at: float):
        self._lookback = lookback_sessions
        self._min_sessions = min_sessions
        self._block_at = block_at

    def evaluate(self, current_iv: Optional[float], daily: List[DailyAtmIv], today: date) -> IvRankGate:
        prior = sorted((d for d in daily if d.session_date < today), key=lambda d: d.session_date)[-self._lookback:]
        common = {"min_sessions": self._min_sessions, "block_at": self._block_at, "sessions": len(prior)}
        if current_iv is None:
            return IvRankGate(status=IvRankGateStatus.OFF, detail="ATM IV unavailable now", **common)
        if len(prior) < self._min_sessions:
            return IvRankGate(
                status=IvRankGateStatus.OFF,
                atm_iv=current_iv,
                detail=f"Off until {self._min_sessions} sessions of stored ATM IV exist ({len(prior)} so far)",
                **common,
            )
        values = [d.atm_iv for d in prior] + [current_iv]
        lo, hi = min(values), max(values)
        rank = 50.0 if hi == lo else (current_iv - lo) / (hi - lo) * 100.0
        status = IvRankGateStatus.BLOCK_BUYING if rank >= self._block_at else IvRankGateStatus.PASS
        return IvRankGate(
            status=status,
            iv_rank=round(rank, 1),
            atm_iv=current_iv,
            detail=f"ATM IV {current_iv:.2f} vs {len(prior)}-session range {lo:.2f}–{hi:.2f}: rank {rank:.0f}",
            **common,
        )
