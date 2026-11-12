from datetime import datetime
from typing import Callable, List

from sqlalchemy import select

from models.market_snapshot import OptionChainSnapshotRecord
from schemas.options import OptionUnderlying
from schemas.shadow_v2 import ChainSnapshotPoint


class ShadowHistoryRepository:
    """Read-only access to stored chain snapshots for the v2 shadow scorer.

    Opens its own short-lived session per call so a failed shadow read can never abort the
    request transaction that records the live prediction log.
    """

    def __init__(self, session_factory: Callable):
        self._session_factory = session_factory

    async def chain_points(
        self, underlying: OptionUnderlying, since: datetime, until: datetime
    ) -> List[ChainSnapshotPoint]:
        table = OptionChainSnapshotRecord
        stmt = (
            select(
                table.captured_at, table.expiry, table.spot, table.strike_window,
                table.near_call_oi, table.near_put_oi, table.near_spot_pcr, table.atm_iv,
            )
            .where(table.underlying == underlying.value)
            .where(table.captured_at >= since)
            .where(table.captured_at <= until)
            .order_by(table.captured_at)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ChainSnapshotPoint(
                captured_at=r.captured_at, expiry=r.expiry, spot=r.spot, strike_window=r.strike_window,
                near_call_oi=r.near_call_oi, near_put_oi=r.near_put_oi,
                near_spot_pcr=r.near_spot_pcr, atm_iv=r.atm_iv,
            )
            for r in rows
        ]
