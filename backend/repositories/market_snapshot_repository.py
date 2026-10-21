from sqlalchemy.ext.asyncio import AsyncSession

from models.market_snapshot import FuturesSnapshotRecord, OptionChainSnapshotRecord
from schemas.market_snapshot import FuturesSnapshotCreate, OptionChainSnapshotCreate


class MarketSnapshotRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_chain(self, payload: OptionChainSnapshotCreate) -> None:
        self._session.add(OptionChainSnapshotRecord(
            underlying=payload.underlying.value,
            expiry=payload.expiry,
            captured_at=payload.captured_at,
            spot=payload.spot,
            atm_strike=payload.atm_strike,
            lot_size=payload.lot_size,
            strike_window=payload.shadow.strike_window,
            rows=[row.model_dump(mode="json") for row in payload.rows],
            near_call_oi=payload.shadow.near_call_oi,
            near_put_oi=payload.shadow.near_put_oi,
            near_spot_pcr=payload.shadow.near_spot_pcr,
            atm_iv=payload.shadow.atm_iv,
            iv_skew_25d=payload.shadow.iv_skew_25d,
            gex_per_1pct=payload.shadow.gex_per_1pct,
            data_version=payload.data_version,
        ))
        await self._session.flush()

    async def add_futures(self, payload: FuturesSnapshotCreate) -> None:
        state = payload.state
        self._session.add(FuturesSnapshotRecord(
            underlying=state.underlying.value,
            contract_symbol=state.contract_symbol,
            expiry=state.expiry,
            captured_at=state.captured_at,
            ltp=state.ltp,
            spot=state.spot,
            basis=state.basis,
            basis_pct=state.basis_pct,
            open_interest=state.open_interest,
            oi_change=state.oi_change,
            volume=state.volume,
            volume_change=state.volume_change,
            price_change=state.price_change,
            cvd_proxy=state.cvd_proxy,
            data_version=payload.data_version,
        ))
        await self._session.flush()
