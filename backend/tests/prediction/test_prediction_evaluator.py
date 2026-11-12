from datetime import datetime, timedelta

import pytest
import pytz

from services.evaluation.prediction_evaluator import (
    EvaluationConfig,
    PredictionEvaluator,
    bucket_of,
    outcome,
    raw_direction,
    render,
)

IST = pytz.timezone("Asia/Kolkata")


def cfg(**kw):
    base = dict(min_samples=200, min_sessions=20, holdout_fraction=0.3, flat_band_pct=0.05, direction_threshold=0.15)
    base.update(kw)
    return EvaluationConfig(**base)


def factor(name, score, weight=0.1, cluster="TREND", status="ACTIVE"):
    return {"name": name, "score": score, "weight": weight, "cluster": cluster, "status": status}


def row(day: int, minute: int = 0, direction="CALL", score=0.3, change=0.2, pnl=None, label="MID_SESSION",
        regime="TRENDING", factors=None, v2=None, mult=1.0):
    at = IST.localize(datetime(2026, 11, 1, 10, 0) + timedelta(days=day, minutes=minute))
    return {
        "predicted_at": at, "direction": direction, "score": score, "session_label": label,
        "regime": {"label": regime, "adx_multiplier": mult},
        "factors": factors if factors is not None else [factor("EMA", 1.0 if score > 0 else -1.0)],
        "shadow_features": {"v2": v2} if v2 is not None else {},
        "spot_change_pct_15m": change, "spot_change_pct_30m": change, "spot_change_pct_60m": change,
        "net_pnl_15m": pnl, "net_pnl_30m": pnl, "net_pnl_60m": pnl,
    }


# ── primitives ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("direction, change, expected", [
    ("CALL", 0.2, "HIT"), ("CALL", -0.2, "MISS"), ("PUT", -0.2, "HIT"), ("PUT", 0.2, "MISS"),
    ("CALL", 0.049, "FLAT"), ("CALL", -0.049, "FLAT"), ("CALL", 0.05, "HIT"),   # band is exclusive
    ("WAIT", 0.5, None), ("NO_TRADE", 0.5, None), ("CALL", None, None),
])
def test_outcome(direction, change, expected):
    assert outcome(direction, change, 0.05) == expected


def test_raw_direction_threshold_multiplier_and_exclusion():
    factors = [factor("A", 0.3, 0.1), factor("B", 0.0, 0.1), factor("C", -1.0, 0.0), factor("D", 1.0, 0.1, status="DISABLED")]
    assert raw_direction(factors, 1.0, 0.15) == "CALL"            # (0.03 + 0) / 0.2 = 0.15 → inclusive
    assert raw_direction(factors, 0.9, 0.15) == "NO_TRADE"        # damped below threshold
    assert raw_direction(factors, 1.0, 0.15, exclude=lambda f: f["name"] == "B") == "CALL"
    assert raw_direction([factor("A", -0.5)], 1.0, 0.15) == "PUT"
    assert raw_direction([], 1.0, 0.15) == "NO_TRADE"


@pytest.mark.parametrize("score, bucket", [
    (0.149, None), (0.15, "0.15-0.25"), (-0.25, "0.25-0.35"), (0.4999, "0.35-0.50"), (0.5, "0.50-1.00"), (1.0, "0.50-1.00"),
])
def test_bucket_boundaries(score, bucket):
    assert bucket_of(score) == bucket


# ── evaluator ────────────────────────────────────────────────────────────────

def test_insufficient_sample_refuses_conclusions_and_withholds_deltas():
    rows = [row(d) for d in range(3)]
    report = PredictionEvaluator(cfg()).evaluate(rows)
    assert report.sufficient is False and report.verdict.startswith("INSUFFICIENT SAMPLE")
    assert "3 sessions < min 20" in report.verdict
    assert all(r.delta is None for r in report.ablation[30])
    assert report.live[30].n == 3                                     # sample sizes still reported
    assert "deltas withheld" in render(report)


def test_unscorable_rows_excluded_and_flats_counted():
    rows = [row(0), row(1, direction="MARKET_CLOSED"), row(2, direction="STALE_DATA"), row(3, change=0.01)]
    report = PredictionEvaluator(cfg(min_samples=1, min_sessions=1)).evaluate(rows)
    assert report.rows_used == 2
    assert report.live[15].n == 1 and report.live[15].flats == 1


def test_chronological_split_keeps_latest_sessions_out_of_sample():
    rows = [row(d, change=0.2) for d in range(7)] + [row(d, change=-0.2) for d in range(7, 10)]
    report = PredictionEvaluator(cfg(min_samples=1, min_sessions=1)).evaluate(rows)
    assert report.holdout_sessions == 3
    assert report.in_sample[30].hit_rate == 1.0 and report.in_sample[30].n == 7
    assert report.out_of_sample[30].hit_rate == 0.0 and report.out_of_sample[30].n == 3


def test_calibration_regime_and_time_buckets():
    rows = [
        row(0, score=0.2, change=0.2, regime="RANGING", label="OPENING"),
        row(1, score=0.2, change=-0.2, regime="RANGING", label="OPENING"),
        row(2, score=0.6, change=0.2, regime="TRENDING", label="MID_SESSION"),
    ]
    report = PredictionEvaluator(cfg(min_samples=1, min_sessions=1)).evaluate(rows)
    assert report.calibration[30]["0.15-0.25"].hit_rate == 0.5
    assert report.calibration[30]["0.50-1.00"].hit_rate == 1.0
    assert report.by_regime[30]["RANGING"].n == 2
    assert report.by_session_label[30]["MID_SESSION"].hits == 1


def test_ablation_measures_hit_rate_change_when_sample_is_sufficient():
    # "Good" points the right way, "Bad" the wrong way and outweighs it; removing Bad fixes every call.
    def factors(up):
        sign = 1.0 if up else -1.0
        return [factor("Good", sign, 0.1, "TREND"), factor("Bad", -sign, 0.2, "OPTIONS")]
    rows = [row(d, change=0.2 if d % 2 == 0 else -0.2, factors=factors(d % 2 == 0)) for d in range(10)]
    report = PredictionEvaluator(cfg(min_samples=5, min_sessions=5)).evaluate(rows)
    assert report.sufficient
    assert report.raw_model[30].hit_rate == 0.0
    by_name = {r.removed: r for r in report.ablation[30]}
    assert by_name["Bad"].delta == pytest.approx(1.0)
    assert by_name["OPTIONS"].kind == "cluster" and by_name["OPTIONS"].delta == pytest.approx(1.0)
    assert by_name["Good"].stats.n == 10


def test_v2_compare_skips_errored_rows_and_pnl_stats():
    rows = [
        row(0, change=0.2, pnl=100.0, v2={"direction": "PUT"}),
        row(1, change=-0.2, pnl=-50.0, v2={"direction": "PUT"}),
        row(2, change=0.2, pnl=None, v2={"direction": "CALL", "error": "boom"}),
    ]
    report = PredictionEvaluator(cfg(min_samples=1, min_sessions=1)).evaluate(rows)
    assert report.v2_rows == 2
    assert report.v2[30].n == 2 and report.v2[30].hits == 1
    assert report.live_raw_on_v2_rows[30].n == 2
    assert report.live_pnl[30].expectancy == 25.0 and report.live_pnl[30].profit_factor == 2.0
