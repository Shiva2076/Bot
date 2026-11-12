from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.market_snapshot import OptionChainSnapshotRecord
from schemas.options import OptionChainRow, OptionType, OptionUnderlying
from schemas.prediction import PredictionDirection

SNAPSHOT_TOLERANCE = timedelta(minutes=10)


class HypotheticalPremiumResolver:
    """Offline-only: nearest option-chain snapshot premiums for research PnL. Not used live."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def premiums_for_horizons(
        self,
        underlying: OptionUnderlying,
        expiry,
        predicted_at: datetime,
        implied_direction: PredictionDirection,
        lot_size: Optional[int],
        horizons_minutes: List[int],
    ) -> Dict[int, Optional[Tuple[float, float, int]]]:
        if implied_direction not in (PredictionDirection.CALL, PredictionDirection.PUT):
            return {minutes: None for minutes in horizons_minutes}
        option_type = OptionType.CE if implied_direction == PredictionDirection.CALL else OptionType.PE
        entry = await self._nearest_snapshot(underlying, expiry, predicted_at)
        if entry is None:
            return {minutes: None for minutes in horizons_minutes}
        entry_premium, resolved_lot = self._atm_premium(entry, option_type, lot_size)
        if entry_premium is None or resolved_lot is None:
            return {minutes: None for minutes in horizons_minutes}
        out: Dict[int, Optional[Tuple[float, float, int]]] = {}
        for minutes in horizons_minutes:
            later_at = predicted_at + timedelta(minutes=minutes)
            later = await self._nearest_snapshot(underlying, expiry, later_at)
            if later is None:
                out[minutes] = None
                continue
            later_premium, _ = self._atm_premium(later, option_type, resolved_lot)
            if later_premium is None:
                out[minutes] = None
                continue
            out[minutes] = (entry_premium, later_premium, resolved_lot)
        return out

    async def _nearest_snapshot(
        self,
        underlying: OptionUnderlying,
        expiry,
        target: datetime,
    ) -> Optional[OptionChainSnapshotRecord]:
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        window_start = target - SNAPSHOT_TOLERANCE
        window_end = target + SNAPSHOT_TOLERANCE
        result = await self._session.execute(
            select(OptionChainSnapshotRecord)
            .where(
                OptionChainSnapshotRecord.underlying == underlying.value,
                OptionChainSnapshotRecord.expiry == expiry,
                OptionChainSnapshotRecord.captured_at >= window_start,
                OptionChainSnapshotRecord.captured_at <= window_end,
            )
            .order_by(OptionChainSnapshotRecord.captured_at.desc())
        )
        rows = list(result.scalars().all())
        best: Optional[OptionChainSnapshotRecord] = None
        best_delta: Optional[timedelta] = None
        for row in rows:
            captured = row.captured_at
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
            delta = abs(captured - target)
            if best_delta is None or delta < best_delta:
                best = row
                best_delta = delta
        return best

    @staticmethod
    def _atm_premium(
        snapshot: OptionChainSnapshotRecord,
        option_type: OptionType,
        lot_size: Optional[int],
    ) -> Tuple[Optional[float], Optional[int]]:
        rows = [OptionChainRow.model_validate(r) for r in snapshot.rows]
        atm = min(rows, key=lambda r: abs(r.strike - snapshot.atm_strike))
        quote = atm.call if option_type == OptionType.CE else atm.put
        if quote is None or quote.ltp <= 0:
            return None, None
        resolved_lot = lot_size if lot_size is not None else snapshot.lot_size
        return quote.ltp, resolved_lot
