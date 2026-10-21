from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.market_snapshot_repository import MarketSnapshotRepository
from schemas.options import OptionUnderlying
from services.options.option_chain_service import OptionChainService
from services.prediction.chain_shadow_calculator import ChainShadowCalculator
from services.prediction.futures_flow_tracker import FuturesFlowTracker
from services.snapshots.market_snapshot_mapper import MarketSnapshotMapper
from services.trading.errors import MarketDataUnavailableError


class MarketSnapshotDependencies(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    chains: OptionChainService
    shadow: ChainShadowCalculator
    futures: FuturesFlowTracker
    mapper: MarketSnapshotMapper


class MarketSnapshotRecorder:
    def __init__(self, deps: MarketSnapshotDependencies):
        self._deps = deps

    async def capture(self, session: AsyncSession, underlying: OptionUnderlying, now: datetime) -> None:
        expiries = (await self._deps.chains.get_expiries(underlying)).expiries
        if not expiries:
            raise MarketDataUnavailableError(f"No live {underlying.value} expiries to snapshot")
        chain = await self._deps.chains.get_chain(underlying, expiries[0])
        repo = MarketSnapshotRepository(session)
        await repo.add_chain(self._deps.mapper.to_chain_create(
            chain, self._deps.shadow.near_rows(chain), self._deps.shadow.calculate(chain), now
        ))
        futures = await self._deps.futures.observe(underlying, chain.spot)
        if futures is not None:
            await repo.add_futures(self._deps.mapper.to_futures_create(futures))
