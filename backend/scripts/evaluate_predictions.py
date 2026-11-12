"""
Phase 2 offline evaluation of logged predictions. Read-only.

Run from backend/:
    .venv\\Scripts\\python -m scripts.evaluate_predictions [--underlying NIFTY] [--json out.json] [--include-pre-fix]

Rows tagged v0_pre_fix are excluded unless --include-pre-fix is given. The verdict refuses
conclusions below evaluation_min_samples / evaluation_min_sessions (config).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from config import settings  # noqa: E402
from database import AsyncSessionLocal  # noqa: E402
from models.prediction_log import PRE_FIX_DATA_VERSION, PredictionLogRecord  # noqa: E402
from services.evaluation.prediction_evaluator import (  # noqa: E402
    HORIZONS,
    EvaluationConfig,
    PredictionEvaluator,
    render,
)
from services.prediction.prediction_scorer import DIRECTION_THRESHOLD  # noqa: E402

COLUMNS = [
    "id", "predicted_at", "underlying", "data_version", "scorer_version", "direction", "score",
    "session_label", "regime", "factors", "shadow_features",
    *[f"spot_change_pct_{h}m" for h in HORIZONS], *[f"net_pnl_{h}m" for h in HORIZONS],
]


async def load(underlying: str, include_pre_fix: bool) -> list:
    table = PredictionLogRecord
    stmt = select(*[getattr(table, c) for c in COLUMNS]).where(table.underlying == underlying)
    if not include_pre_fix:
        stmt = stmt.where(table.data_version != PRE_FIX_DATA_VERSION)
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt.order_by(table.predicted_at))
        return [dict(row._mapping) for row in result]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--json", help="also write the full report as JSON to this path")
    parser.add_argument("--include-pre-fix", action="store_true")
    args = parser.parse_args()

    rows = await load(args.underlying, args.include_pre_fix)
    report = PredictionEvaluator(EvaluationConfig(
        min_samples=settings.evaluation_min_samples,
        min_sessions=settings.evaluation_min_sessions,
        holdout_fraction=settings.evaluation_holdout_fraction,
        flat_band_pct=settings.prediction_outcome_flat_band_pct,
        direction_threshold=DIRECTION_THRESHOLD,
    )).evaluate(rows)
    print(render(report))
    if args.json:
        Path(args.json).write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"JSON written to {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
