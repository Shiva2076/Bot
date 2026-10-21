from database import AsyncSessionLocal
from repositories.trade_repository import TradeRepository
from schemas.personal_trade import PaperTradeOpened, TradeExitRequest
from services.personal.pnl_calculator import PnlCalculator
from services.personal.trade_mapper import PersonalTradeMapper


class PaperTradeRecorder:
    def __init__(self, mapper: PersonalTradeMapper):
        self._mapper = mapper

    async def record_open(self, opened: PaperTradeOpened) -> int:
        async with AsyncSessionLocal() as session:
            trade = await TradeRepository(session).add(self._mapper.paper_to_entity(opened))
            await session.commit()
            return trade.id

    async def record_close(self, trade_id: int, request: TradeExitRequest) -> None:
        async with AsyncSessionLocal() as session:
            trade = await TradeRepository(session).get(trade_id)
            self._mapper.apply_exit(trade, request)
            await session.commit()


paper_trade_recorder = PaperTradeRecorder(PersonalTradeMapper(PnlCalculator()))
