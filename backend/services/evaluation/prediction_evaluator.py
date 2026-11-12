"""
Offline evaluation of logged predictions (Phase 2 harness).

Works on plain dict rows shaped like prediction_logs, so it is testable without a database.
Rows tagged v0_pre_fix are excluded by the caller/loader by default.

What it reports, always with sample sizes:
  * live directional hit rate and net expectancy per horizon
  * calibration: |score| bucket vs hit rate
  * per-regime and per-time-bucket (session label) hit rate
  * chronological split: earlier sessions (in-sample) vs latest sessions (out-of-sample)
  * ablation: recompute the raw factor score without each factor / cluster
  * v2 shadow vs live raw signal on the same rows

It refuses to draw conclusions below the configured minimum samples/sessions: the verdict
says INSUFFICIENT and no delta is labelled as better or worse.
"""
from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pytz
from pydantic import BaseModel, Field

IST = pytz.timezone("Asia/Kolkata")
HORIZONS = (15, 30, 60)
SCORE_BUCKETS: Tuple[Tuple[float, float], ...] = ((0.15, 0.25), (0.25, 0.35), (0.35, 0.50), (0.50, 1.01))
DIRECTIONAL = ("CALL", "PUT")
UNSCORABLE = ("MARKET_CLOSED", "STALE_DATA", "UNKNOWN_FRESHNESS")
ACTIVE = "ACTIVE"


class EvaluationConfig(BaseModel):
    min_samples: int
    min_sessions: int
    holdout_fraction: float
    flat_band_pct: float
    direction_threshold: float


class HitStats(BaseModel):
    n: int = 0          # directional calls with a non-flat outcome
    hits: int = 0
    flats: int = 0

    @property
    def hit_rate(self) -> Optional[float]:
        return round(self.hits / self.n, 4) if self.n else None

    def add(self, result: Optional[str]) -> None:
        if result == "FLAT":
            self.flats += 1
        elif result in ("HIT", "MISS"):
            self.n += 1
            self.hits += result == "HIT"


class PnlStats(BaseModel):
    n: int = 0
    total: float = 0.0
    gross_win: float = 0.0
    gross_loss: float = 0.0

    @property
    def expectancy(self) -> Optional[float]:
        return round(self.total / self.n, 2) if self.n else None

    @property
    def profit_factor(self) -> Optional[float]:
        if not self.n or self.gross_loss == 0:
            return None
        return round(self.gross_win / abs(self.gross_loss), 3)

    def add(self, value: Optional[float]) -> None:
        if value is None:
            return
        self.n += 1
        self.total += value
        if value > 0:
            self.gross_win += value
        else:
            self.gross_loss += value


class AblationRow(BaseModel):
    removed: str
    kind: str                    # "factor" or "cluster"
    stats: HitStats
    delta: Optional[float]       # hit-rate change vs the full recomputed model


class EvaluationReport(BaseModel):
    rows_used: int
    sessions: int
    first_session: Optional[str] = None
    last_session: Optional[str] = None
    sufficient: bool
    verdict: str
    live: Dict[int, HitStats] = Field(default_factory=dict)
    live_pnl: Dict[int, PnlStats] = Field(default_factory=dict)
    calibration: Dict[int, Dict[str, HitStats]] = Field(default_factory=dict)
    by_regime: Dict[int, Dict[str, HitStats]] = Field(default_factory=dict)
    by_session_label: Dict[int, Dict[str, HitStats]] = Field(default_factory=dict)
    in_sample: Dict[int, HitStats] = Field(default_factory=dict)
    out_of_sample: Dict[int, HitStats] = Field(default_factory=dict)
    holdout_sessions: int = 0
    raw_model: Dict[int, HitStats] = Field(default_factory=dict)
    ablation: Dict[int, List[AblationRow]] = Field(default_factory=dict)
    v2_rows: int = 0
    v2: Dict[int, HitStats] = Field(default_factory=dict)
    live_raw_on_v2_rows: Dict[int, HitStats] = Field(default_factory=dict)


# ── primitives ───────────────────────────────────────────────────────────────

def outcome(direction: Optional[str], change_pct: Optional[float], flat_band_pct: float) -> Optional[str]:
    if direction not in DIRECTIONAL or change_pct is None:
        return None
    if abs(change_pct) < flat_band_pct:
        return "FLAT"
    up = change_pct > 0
    return "HIT" if (direction == "CALL") == up else "MISS"


def raw_direction(
    factors: Sequence[dict], adx_multiplier: float, threshold: float,
    exclude: Callable[[dict], bool] = lambda f: False,
) -> str:
    active = [f for f in factors if f.get("status") == ACTIVE and (f.get("weight") or 0) > 0 and not exclude(f)]
    total = sum(f["weight"] for f in active)
    if total <= 0:
        return "NO_TRADE"
    score = sum(f["score"] * f["weight"] for f in active) / total * adx_multiplier
    if score >= threshold:
        return "CALL"
    if score <= -threshold:
        return "PUT"
    return "NO_TRADE"


def session_of(row: dict) -> str:
    at: datetime = row["predicted_at"]
    if at.tzinfo is None:
        at = pytz.utc.localize(at)
    return at.astimezone(IST).date().isoformat()


def bucket_of(score: float) -> Optional[str]:
    magnitude = abs(score)
    for lo, hi in SCORE_BUCKETS:
        if lo <= magnitude < hi:
            return f"{lo:.2f}-{min(hi, 1.0):.2f}"
    return None


def _change(row: dict, h: int) -> Optional[float]:
    return row.get(f"spot_change_pct_{h}m")


def _v2(row: dict) -> Optional[dict]:
    v2 = (row.get("shadow_features") or {}).get("v2")
    return v2 if v2 and not v2.get("error") else None


# ── evaluator ────────────────────────────────────────────────────────────────

class PredictionEvaluator:
    def __init__(self, config: EvaluationConfig):
        self._c = config

    def evaluate(self, rows: Iterable[dict]) -> EvaluationReport:
        rows = sorted(
            (r for r in rows if r.get("direction") not in UNSCORABLE),
            key=lambda r: r["predicted_at"],
        )
        sessions = sorted({session_of(r) for r in rows})
        holdout = self._holdout_sessions(sessions)
        report = EvaluationReport(
            rows_used=len(rows),
            sessions=len(sessions),
            first_session=sessions[0] if sessions else None,
            last_session=sessions[-1] if sessions else None,
            sufficient=False,
            verdict="",
            holdout_sessions=len(holdout),
        )
        for h in HORIZONS:
            self._live(report, rows, h, holdout)
            self._ablation(report, rows, h)
            self._v2_compare(report, rows, h)
        report.v2_rows = sum(1 for r in rows if _v2(r))
        report.sufficient, report.verdict = self._verdict(report)
        if not report.sufficient:
            for rows_h in report.ablation.values():
                for row in rows_h:
                    row.delta = None
        return report

    def _holdout_sessions(self, sessions: List[str]) -> set:
        if len(sessions) < 2:
            return set()
        k = max(1, int(round(len(sessions) * self._c.holdout_fraction)))
        return set(sessions[-k:])

    def _live(self, report: EvaluationReport, rows: List[dict], h: int, holdout: set) -> None:
        live, pnl = HitStats(), PnlStats()
        calibration: Dict[str, HitStats] = defaultdict(HitStats)
        regime: Dict[str, HitStats] = defaultdict(HitStats)
        label: Dict[str, HitStats] = defaultdict(HitStats)
        ins, oos = HitStats(), HitStats()
        for row in rows:
            result = outcome(row.get("direction"), _change(row, h), self._c.flat_band_pct)
            if result is None:
                continue
            live.add(result)
            pnl.add(row.get(f"net_pnl_{h}m"))
            bucket = bucket_of(row.get("score") or 0.0)
            if bucket:
                calibration[bucket].add(result)
            regime[((row.get("regime") or {}).get("label")) or "UNKNOWN"].add(result)
            label[row.get("session_label") or "UNKNOWN"].add(result)
            (oos if session_of(row) in holdout else ins).add(result)
        report.live[h], report.live_pnl[h] = live, pnl
        report.calibration[h] = dict(sorted(calibration.items()))
        report.by_regime[h] = dict(sorted(regime.items()))
        report.by_session_label[h] = dict(sorted(label.items()))
        report.in_sample[h], report.out_of_sample[h] = ins, oos

    def _model_stats(self, rows: List[dict], h: int, exclude: Callable[[dict], bool]) -> HitStats:
        stats = HitStats()
        for row in rows:
            mult = (row.get("regime") or {}).get("adx_multiplier", 1.0) or 1.0
            direction = raw_direction(row.get("factors") or [], mult, self._c.direction_threshold, exclude)
            stats.add(outcome(direction, _change(row, h), self._c.flat_band_pct))
        return stats

    def _ablation(self, report: EvaluationReport, rows: List[dict], h: int) -> None:
        base = self._model_stats(rows, h, lambda f: False)
        report.raw_model[h] = base
        names = sorted({f["name"] for r in rows for f in (r.get("factors") or []) if f.get("status") == ACTIVE})
        clusters = sorted({f["cluster"] for r in rows for f in (r.get("factors") or []) if f.get("status") == ACTIVE})
        out: List[AblationRow] = []
        for kind, values, key in (("factor", names, "name"), ("cluster", clusters, "cluster")):
            for value in values:
                stats = self._model_stats(rows, h, lambda f, k=key, v=value: f.get(k) == v)
                delta = (
                    round(stats.hit_rate - base.hit_rate, 4)
                    if stats.hit_rate is not None and base.hit_rate is not None else None
                )
                out.append(AblationRow(removed=value, kind=kind, stats=stats, delta=delta))
        report.ablation[h] = out

    def _v2_compare(self, report: EvaluationReport, rows: List[dict], h: int) -> None:
        v2_stats, live_stats = HitStats(), HitStats()
        for row in rows:
            v2 = _v2(row)
            if v2 is None:
                continue
            v2_stats.add(outcome(v2.get("direction"), _change(row, h), self._c.flat_band_pct))
            mult = (row.get("regime") or {}).get("adx_multiplier", 1.0) or 1.0
            live_dir = raw_direction(row.get("factors") or [], mult, self._c.direction_threshold)
            live_stats.add(outcome(live_dir, _change(row, h), self._c.flat_band_pct))
        report.v2[h], report.live_raw_on_v2_rows[h] = v2_stats, live_stats

    def _verdict(self, report: EvaluationReport) -> Tuple[bool, str]:
        smallest = min((s.n for s in report.live.values()), default=0)
        problems = []
        if report.sessions < self._c.min_sessions:
            problems.append(f"{report.sessions} sessions < min {self._c.min_sessions}")
        if smallest < self._c.min_samples:
            problems.append(f"{smallest} directional outcomes at the thinnest horizon < min {self._c.min_samples}")
        if problems:
            return False, "INSUFFICIENT SAMPLE - no conclusions: " + "; ".join(problems)
        return True, "Sample meets the configured minimum; results are still estimates, not proof."


# ── text rendering ───────────────────────────────────────────────────────────

def _fmt(stats: HitStats) -> str:
    rate = "   -  " if stats.hit_rate is None else f"{stats.hit_rate * 100:5.1f}%"
    return f"{rate} (n={stats.n}, flat={stats.flats})"


def render(report: EvaluationReport) -> str:
    lines = [
        "PREDICTION EVALUATION (v0_pre_fix excluded)",
        f"rows used {report.rows_used} | sessions {report.sessions} "
        f"({report.first_session} .. {report.last_session}) | v2 shadow rows {report.v2_rows}",
        f"VERDICT: {report.verdict}",
        "",
    ]
    for h in HORIZONS:
        if h not in report.live:
            continue
        pnl = report.live_pnl[h]
        lines += [
            f"== {h}m horizon ==",
            f"live direction      {_fmt(report.live[h])}   net/lot expectancy {pnl.expectancy} "
            f"(n={pnl.n}), profit factor {pnl.profit_factor}",
            f"in-sample           {_fmt(report.in_sample[h])}",
            f"out-of-sample       {_fmt(report.out_of_sample[h])}   (latest {report.holdout_sessions} sessions)",
            "calibration |score|: " + "; ".join(f"{k} {_fmt(v)}" for k, v in report.calibration[h].items()),
            "by regime:          " + "; ".join(f"{k} {_fmt(v)}" for k, v in report.by_regime[h].items()),
            "by time bucket:     " + "; ".join(f"{k} {_fmt(v)}" for k, v in report.by_session_label[h].items()),
            f"raw model (no gates){_fmt(report.raw_model[h])}",
            f"v2 shadow           {_fmt(report.v2[h])}  vs live raw on same rows {_fmt(report.live_raw_on_v2_rows[h])}",
            "ablation (hit-rate change when removed" + ("" if report.sufficient else "; deltas withheld") + "):",
        ]
        for row in report.ablation[h]:
            delta = "  n/a " if row.delta is None else f"{row.delta * 100:+5.1f}pp"
            lines.append(f"   - {row.kind:<7} {row.removed:<34} {delta}  {_fmt(row.stats)}")
        lines.append("")
    return "\n".join(lines)
