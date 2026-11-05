"""Offline: rebuild prediction_research_outcomes from gated prediction_logs. Never used live."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import get_settings
from database import AsyncSessionLocal, create_tables
from schemas.costs import CostConfig
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.prediction.prediction_outcome_calculator import PredictionOutcomeCalculator
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.research.prediction_research_builder import PredictionResearchBuilder


async def main() -> None:
    settings = get_settings()
    await create_tables()
    costs = PaperCostCalculator(
        CostConfig(
            brokerage_pct=settings.cost_brokerage_pct,
            brokerage_flat=settings.cost_brokerage_flat,
            exchange_txn_pct=settings.cost_exchange_txn_pct,
            sebi_pct=settings.cost_sebi_pct,
            stamp_duty_buy_pct=settings.cost_stamp_duty_buy_pct,
            stt_sell_pct=settings.cost_stt_sell_pct,
            gst_pct=settings.cost_gst_pct,
            slippage_bps=settings.cost_slippage_bps,
        )
    )
    builder = PredictionResearchBuilder(
        scorer=PredictionScorer(),
        outcome_calculator=PredictionOutcomeCalculator(settings.prediction_outcome_flat_band_pct, costs),
        costs=costs,
    )
    async with AsyncSessionLocal() as session:
        written = await builder.rebuild(session)
        await session.commit()
    print(f"prediction_research_outcomes upserted: {written}")


if __name__ == "__main__":
    asyncio.run(main())
