"""
Read-only report: gated score hit-rate vs SYSTEM_SIGNAL trades, by underlying and wait trigger.

Prints NOT ENOUGH DATA below prediction_research_min_sessions. Draws no conclusion.
"""

import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from config import get_settings
from database import AsyncSessionLocal, create_tables
from models.prediction_research_outcome import PredictionResearchOutcomeRecord
from models.trade import Trade
from schemas.order_entry import OrderSource
from schemas.prediction_log import DirectionResult


async def main() -> None:
    settings = get_settings()
    min_sessions = settings.prediction_research_min_sessions
    await create_tables()
    async with AsyncSessionLocal() as session:
        research = list(
            (
                await session.execute(select(PredictionResearchOutcomeRecord))
            ).scalars().all()
        )
        trades = list(
            (
                await session.execute(
                    select(Trade).where(Trade.order_source == OrderSource.SYSTEM_SIGNAL.value)
                )
            ).scalars().all()
        )

    buckets: Dict[Tuple[str, Optional[str]], list] = defaultdict(list)
    for row in research:
        buckets[(row.underlying, row.premarket_wait_trigger)].append(row)

    print(f"min_sessions={min_sessions}")
    print("underlying | wait_trigger | sessions | rows | gated_hit_rate_15m | system_signal_trades | system_win_rate")
    print("-" * 110)

    for (underlying, trigger), rows in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1] or "")):
        sessions = {row.predicted_at.date() for row in rows}
        hits = 0
        scored = 0
        for row in rows:
            if row.spot_result_15m in (DirectionResult.HIT.value, DirectionResult.MISS.value):
                scored += 1
                if row.spot_result_15m == DirectionResult.HIT.value:
                    hits += 1
        gated_rate = f"{(hits / scored * 100):.1f}%" if scored else "n/a"
        related = [t for t in trades if underlying.lower() in t.symbol.lower()]
        wins = sum(1 for t in related if t.pnl is not None and t.pnl > 0)
        closed = sum(1 for t in related if t.pnl is not None)
        sys_rate = f"{(wins / closed * 100):.1f}%" if closed else "n/a"
        if len(sessions) < min_sessions:
            print(
                f"{underlying} | {trigger or 'NULL'} | {len(sessions)} | {len(rows)} | "
                f"NOT ENOUGH DATA | {len(related)} | {sys_rate}"
            )
            continue
        print(
            f"{underlying} | {trigger or 'NULL'} | {len(sessions)} | {len(rows)} | "
            f"{gated_rate} | {len(related)} | {sys_rate}"
        )
    print("NOTE: below min_sessions this script prints NOT ENOUGH DATA and draws no conclusion.")


if __name__ == "__main__":
    asyncio.run(main())
