"""
Phase 2 shadow scorer (v2.0).

Starts from the live (v1.x) factor list and replaces the factors Phase 2 rebuilds:

  live factor            v2 replacement
  ---------------------  -----------------------------------------------------------
  Put-Call Ratio         Δ Near-Spot PCR over a window (stored snapshots)
  Pre-Market Bias        half-life decay; zero weight when its own action is WAIT/NO_TRADE
  VWAP (<interval>)      VWAP from near-month futures volume
  Relative Volume (...)  same-time-of-day RVOL from futures volume, direction-confirming only
  ΔOI Dynamics           ΔOI buildup modes from stored snapshots + spot direction
  IV Rank                removed as a vote; becomes a gate on buying (OFF until enough sessions)

Everything else (agents, ADX multiplier, Max Pain, OI walls, trend, VIX, breadth, MTF) is
carried over unchanged. The result is logged in shadow_features.v2 only: it never changes the
live direction, the gates, the UI or orders.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Awaitable, Callable, List, Optional, Protocol, Tuple

from schemas.options import OptionUnderlying
from schemas.prediction import (
    FactorStatus,
    IvRankGateStatus,
    OptionPrediction,
    PredictionDirection,
    PredictionFactor,
    ShadowScoreV2,
)
from schemas.shadow_v2 import ChainSnapshotPoint, ShadowV2Config, ShadowV2Inputs
from schemas.trading import Candle
from services.prediction.factor_contribution_annotator import FactorContributionAnnotator
from services.prediction.prediction_scorer import PredictionScorer
from services.prediction.v2.futures_volume_analyzer import FuturesVolumeAnalyzer
from services.prediction.v2.iv_rank_gate import IvRankGateEvaluator
from services.prediction.v2.oi_buildup_analyzer import OiBuildupAnalyzer
from services.prediction.v2.pcr_change_analyzer import PcrChangeAnalyzer
from services.prediction.v2.premarket_half_life import IST, PremarketHalfLifeAnalyzer
from services.prediction.v2.snapshot_history import daily_atm_iv_series

LIVE_PCR = "Put-Call Ratio"
LIVE_PREMARKET = "Pre-Market Bias"
LIVE_DELTA_OI = "ΔOI Dynamics"
LIVE_IV_RANK = "IV Rank"
LIVE_VWAP_PREFIX = "VWAP ("
LIVE_RVOL_PREFIX = "Relative Volume ("
IV_RANK_GATE_REASON = "IV_RANK_HIGH"
DIRECTIONAL = {PredictionDirection.CALL, PredictionDirection.PUT}


class ShadowHistorySource(Protocol):
    async def chain_points(
        self, underlying: OptionUnderlying, since: datetime, until: datetime
    ) -> List[ChainSnapshotPoint]: ...


FuturesCandleSource = Callable[[OptionUnderlying], Awaitable[Optional[Tuple[str, List[Candle]]]]]


class ShadowScorerV2:
    def __init__(
        self,
        config: ShadowV2Config,
        pcr: PcrChangeAnalyzer,
        premarket: PremarketHalfLifeAnalyzer,
        futures_volume: FuturesVolumeAnalyzer,
        oi_buildup: OiBuildupAnalyzer,
        iv_gate: IvRankGateEvaluator,
        scorer: PredictionScorer,
        annotator: FactorContributionAnnotator,
        weight_budget: float,
        history: Optional[ShadowHistorySource] = None,
        futures_candles: Optional[FuturesCandleSource] = None,
    ):
        self._config = config
        self._pcr = pcr
        self._premarket = premarket
        self._futures_volume = futures_volume
        self._oi_buildup = oi_buildup
        self._iv_gate = iv_gate
        self._scorer = scorer
        self._annotator = annotator
        self._budget = weight_budget
        self._history = history
        self._futures_candles = futures_candles

    @property
    def version(self) -> str:
        return self._config.version

    async def evaluate(self, prediction: OptionPrediction) -> ShadowScoreV2:
        """Never raises: a failure is recorded in the result so the live prediction is unaffected."""
        try:
            inputs = await self.load_inputs(prediction)
            return self.compose(prediction, inputs)
        except Exception as exc:
            return ShadowScoreV2(version=self.version, error=f"{type(exc).__name__}: {exc}")

    async def load_inputs(self, prediction: OptionPrediction) -> ShadowV2Inputs:
        now = prediction.generated_at
        notes: List[str] = []
        chain_points, futures = await asyncio.gather(
            self._load_history(prediction.underlying, now, notes),
            self._load_futures(prediction.underlying, notes),
        )
        symbol, candles = futures if futures is not None else (None, None)
        today = now.astimezone(IST).date()
        same_expiry = [p for p in chain_points if p.expiry == prediction.expiry]
        return ShadowV2Inputs(
            chain_history=same_expiry,
            daily_atm_iv=[d for d in daily_atm_iv_series(chain_points) if d.session_date < today],
            futures_symbol=symbol,
            futures_candles=candles,
            notes=notes,
        )

    def compose(self, prediction: OptionPrediction, inputs: ShadowV2Inputs) -> ShadowScoreV2:
        now = prediction.generated_at
        chain = prediction.shadow.chain
        live = {f.name: f for f in prediction.factors}

        pcr = self._pcr.analyze(chain.near_spot_pcr, chain.strike_window, now, inputs.chain_history)
        premarket = self._premarket.analyze(live.get(LIVE_PREMARKET), prediction.premarket_action, now)
        vwap, rvol = self._futures_volume.analyze(inputs.futures_candles, now, inputs.futures_symbol)
        oi = self._oi_buildup.analyze(
            prediction.spot, chain.near_call_oi, chain.near_put_oi, chain.strike_window, now, inputs.chain_history
        )
        replacements = {"pcr": pcr, "premarket": premarket, "vwap": vwap, "rvol": rvol, "oi": oi}

        factors: List[PredictionFactor] = []
        placed = set()
        for factor in prediction.factors:
            slot = self._slot(factor.name)
            if slot == "drop":
                continue
            if slot is not None:
                factors.append(replacements[slot])
                placed.add(slot)
            else:
                factors.append(factor.model_copy(update={"contribution": 0.0, "contribution_pct": 0.0}))
        factors.extend(replacements[s] for s in ("pcr", "premarket", "vwap", "rvol", "oi") if s not in placed)

        raw = self._scorer.score(factors)
        adjusted = round(raw * prediction.regime.adx_multiplier, 3)
        direction = self._scorer.direction(adjusted)
        iv_gate = self._iv_gate.evaluate(chain.atm_iv, inputs.daily_atm_iv, now.astimezone(IST).date())
        gate = None
        if iv_gate.status == IvRankGateStatus.BLOCK_BUYING and direction in DIRECTIONAL:
            direction = PredictionDirection.NO_TRADE
            gate = IV_RANK_GATE_REASON
        active_weight = sum(f.weight for f in factors if f.status == FactorStatus.ACTIVE and f.weight > 0)
        return ShadowScoreV2(
            version=self.version,
            raw_score=raw,
            adjusted_score=adjusted,
            direction=direction,
            gate=gate,
            coverage=round(min(1.0, active_weight / self._budget), 3) if self._budget > 0 else 0.0,
            iv_rank_gate=iv_gate,
            factors=self._annotator.annotate(factors),
            notes=inputs.notes,
        )

    @staticmethod
    def _slot(name: str) -> Optional[str]:
        if name == LIVE_PCR:
            return "pcr"
        if name == LIVE_PREMARKET:
            return "premarket"
        if name == LIVE_DELTA_OI:
            return "oi"
        if name == LIVE_IV_RANK:
            return "drop"
        if name.startswith(LIVE_VWAP_PREFIX):
            return "vwap"
        if name.startswith(LIVE_RVOL_PREFIX):
            return "rvol"
        return None

    async def _load_history(self, underlying: OptionUnderlying, now: datetime, notes: List[str]) -> List[ChainSnapshotPoint]:
        if self._history is None:
            notes.append("no snapshot history source configured")
            return []
        # Calendar-day span generous enough to contain `iv_rank_lookback_sessions` sessions.
        days = int(self._config.iv_rank_lookback_sessions * 1.6) + 7
        try:
            return await self._history.chain_points(underlying, now - timedelta(days=days), now)
        except Exception as exc:
            notes.append(f"snapshot history unavailable: {type(exc).__name__}")
            return []

    async def _load_futures(self, underlying: OptionUnderlying, notes: List[str]) -> Optional[Tuple[str, List[Candle]]]:
        if self._futures_candles is None:
            notes.append("no futures candle source configured")
            return None
        try:
            return await self._futures_candles(underlying)
        except Exception as exc:
            notes.append(f"futures candles unavailable: {type(exc).__name__}")
            return None
