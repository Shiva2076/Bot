from datetime import datetime
from typing import List

from schemas.market_snapshot import FuturesSnapshotCreate, OptionChainSnapshotCreate
from schemas.options import OptionChain, OptionChainRow
from schemas.prediction import ChainShadowFeatures, FuturesFlowState


class MarketSnapshotMapper:
    def __init__(self, data_version: str):
        self._data_version = data_version

    def to_chain_create(
        self,
        chain: OptionChain,
        near_rows: List[OptionChainRow],
        shadow: ChainShadowFeatures,
        captured_at: datetime,
    ) -> OptionChainSnapshotCreate:
        return OptionChainSnapshotCreate(
            underlying=chain.underlying,
            expiry=chain.expiry,
            captured_at=captured_at,
            spot=chain.spot,
            atm_strike=chain.atm_strike,
            lot_size=chain.lot_size,
            rows=near_rows,
            shadow=shadow,
            data_version=self._data_version,
        )

    def to_futures_create(self, state: FuturesFlowState) -> FuturesSnapshotCreate:
        return FuturesSnapshotCreate(state=state, data_version=self._data_version)
