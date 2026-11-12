import asyncio
import time
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Dict, Optional, Tuple

import pytz
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.options import OptionChain, OptionType, OptionUnderlying
from schemas.premarket import BreadthSnapshot, IndiaVixSnapshot
from schemas.prediction import (
    ChartStructureFeatures,
    GateReason,
    IntradayIndicators,
    OptionPrediction,
    PredictionDirection,
    ShadowFeatures,
    SuggestedContract,
)
from schemas.trading import Tick
from services.options.option_chain_service import UNDERLYING_SPOT_SYMBOLS, OptionChainService
from services.prediction.prediction_dependencies import PredictionAnalyzers, PredictionSources
from services.prediction.prediction_log_recorder import PredictionLogRecorder
from services.trading.failover_market_data import FailoverMarketData

if TYPE_CHECKING:
    from services.prediction.v2.shadow_scorer_v2 import ShadowScorerV2

IST = pytz.timezone("Asia/Kolkata")
OPTION_TYPE_BY_DIRECTION: Dict[PredictionDirection, OptionType] = {
    PredictionDirection.CALL: OptionType.CE,
    PredictionDirection.PUT: OptionType.PE,
}
NON_ACTIONABLE = {
    PredictionDirection.NO_TRADE,
    PredictionDirection.WAIT,
    PredictionDirection.MARKET_CLOSED,
    PredictionDirection.STALE_DATA,
    PredictionDirection.UNKNOWN_FRESHNESS,
}

GATE_DIRECTION = {
    GateReason.MARKET_CLOSED: PredictionDirection.MARKET_CLOSED,
    GateReason.STALE_DATA: PredictionDirection.STALE_DATA,
    GateReason.UNKNOWN_FRESHNESS: PredictionDirection.UNKNOWN_FRESHNESS,
}


class OptionPredictionService:
    def __init__(
        self,
        chain_service: OptionChainService,
        market_data: FailoverMarketData,
        sources: PredictionSources,
        analyzers: PredictionAnalyzers,
        cache_seconds: float,
        log_recorder: PredictionLogRecorder,
        shadow_v2: Optional["ShadowScorerV2"] = None,
    ):
        self._chain_service = chain_service
        self._market_data = market_data
        self._sources = sources
        self._analyzers = analyzers
        self._cache_seconds = cache_seconds
        self._log_recorder = log_recorder
        self._shadow_v2 = shadow_v2
        self._cache: Dict[Tuple[OptionUnderlying, date], Tuple[float, OptionPrediction]] = {}

    async def predict(
        self,
        underlying: OptionUnderlying,
        expiry: date,
        session: Optional[AsyncSession] = None,
        force: bool = False,
    ) -> OptionPrediction:
        key = (underlying, expiry)
        if not force:
            cached = self._cache.get(key)
            if cached and time.time() - cached[0] < self._cache_seconds:
                return cached[1]
        prediction = await self._build(underlying, expiry)
        if self._shadow_v2 is not None:
            # Shadow only: attached for logging/evaluation; live direction, gates and contract untouched.
            v2 = await self._shadow_v2.evaluate(prediction)
            prediction = prediction.model_copy(
                update={"shadow": prediction.shadow.model_copy(update={"v2": v2})}
            )
        if session is not None:
            try:
                log_id = await self._log_recorder.record(session, prediction)
                prediction = prediction.model_copy(update={"log_id": log_id})
            except Exception as exc:
                # Keep the prediction panel usable when Postgres/Supabase is unreachable.
                print(f"Prediction log skipped: {exc}")
                await session.rollback()
        self._cache[key] = (time.time(), prediction)
        return prediction

    async def _build(self, underlying: OptionUnderlying, expiry: date) -> OptionPrediction:
        spot_symbol = UNDERLYING_SPOT_SYMBOLS[underlying]
        # Request clock for date/premarket only — never reuse for quote freshness.
        request_at = datetime.now(timezone.utc)
        today = request_at.astimezone(IST).date()

        # Angel spot must win the rate-limit queue before the option-chain quote flood.
        spot_tick = await self._spot_tick_for_freshness(spot_symbol)

        chain, consensus, indicators, premarket, indicators_15m, vix_snapshot, breadth_snapshot = (
            await asyncio.gather(
                self._chain_service.get_chain(underlying, expiry),
                self._sources.agents.get(spot_symbol),
                self._sources.indicators.get(spot_symbol),
                self._sources.premarket.bundle(request_at),
                self._optional_indicators_15m(spot_symbol),
                self._optional_vix(),
                self._optional_breadth(),
            )
        )

        # Freshness boundary: clock taken after quotes/ticks are in hand.
        evaluated_at = datetime.now(timezone.utc)
        market = self._analyzers.market_gate.evaluate(evaluated_at, [spot_tick])
        metrics = self._analyzers.metrics.calculate(chain)
        factors = [
            self._analyzers.agents.analyze(consensus),
            *self._analyzers.chain.analyze(metrics, chain.spot, expiry, today),
            *self._analyzers.technical.analyze(indicators),
            *premarket.factors,
        ]
        if self._analyzers.vix is not None and vix_snapshot is not None:
            factors.append(self._analyzers.vix.analyze(vix_snapshot))
        if self._analyzers.breadth is not None and breadth_snapshot is not None:
            factors.append(self._analyzers.breadth.analyze(breadth_snapshot))
        if self._analyzers.mtf is not None:
            mtf_factor = self._analyzers.mtf.analyze(indicators, indicators_15m)
            if mtf_factor is not None:
                factors.append(mtf_factor)

        adx_mult = self._analyzers.adx_multiplier.multiplier(indicators.adx)
        raw_score = self._analyzers.scorer.score(factors)
        adjusted_score = round(raw_score * adx_mult, 3)
        ctx = self._analyzers.time_context.analyze(expiry, evaluated_at)
        signal_score = self._analyzers.scorer.signal_score(adjusted_score, ctx.confidence_modifier)
        coverage = self._analyzers.wait_gate.coverage(factors)
        cluster_scores = self._analyzers.clusters.summarize(factors)
        factors = self._analyzers.contributions.annotate(factors)
        cluster_scores = self._analyzers.contributions.annotate_clusters(factors, cluster_scores)

        direction = self._analyzers.scorer.direction(adjusted_score)
        gate_reason = GateReason.NONE
        contract = None
        if market.blocks_action:
            direction = GATE_DIRECTION[market.gate_reason]
            gate_reason = market.gate_reason
        else:
            if ctx.is_expiry_day and ctx.session == "PRE_CLOSE" and signal_score < 75:
                direction = PredictionDirection.WAIT
                gate_reason = GateReason.EXPIRY_PRE_CLOSE
            else:
                wait_reason = self._analyzers.wait_gate.evaluate(
                    factors=factors,
                    cluster_scores=cluster_scores,
                    indicators_5m=indicators,
                    indicators_15m=indicators_15m,
                    premarket_action=premarket.recommended_action,
                    signal_score=signal_score,
                    invalid_data=False,
                )
                if wait_reason != GateReason.NONE:
                    direction = PredictionDirection.WAIT
                    gate_reason = wait_reason
            contract = self._suggest(chain, direction, indicators)
            if contract is not None:
                evaluated_at = datetime.now(timezone.utc)
                market = self._analyzers.market_gate.evaluate(
                    evaluated_at, [spot_tick], [contract.quote]
                )
                if market.blocks_action:
                    direction = GATE_DIRECTION[market.gate_reason]
                    gate_reason = market.gate_reason
                    contract = None

        chain_shadow = self._analyzers.shadow.calculate(chain)
        chart_shadow = await self._chart_shadow(spot_symbol, indicators, evaluated_at)
        regime = self._analyzers.regime.classify(indicators.adx, vix_snapshot, chain_shadow.atm_iv)
        regime = regime.model_copy(update={"adx_multiplier": adx_mult})

        freshness_diagnostics = None
        if gate_reason in (GateReason.STALE_DATA, GateReason.UNKNOWN_FRESHNESS):
            freshness_diagnostics = market.quotes

        return OptionPrediction(
            underlying=underlying,
            expiry=expiry,
            spot=chain.spot,
            lot_size=chain.lot_size,
            direction=direction,
            score=adjusted_score,
            raw_score=raw_score,
            signal_score=signal_score,
            confidence=signal_score,
            time_modifier=ctx.confidence_modifier,
            coverage=coverage,
            gate_reason=gate_reason,
            session_status=market.session_status,
            data_freshness=market.data_freshness,
            quote_timestamps=market.quotes,
            contract=contract,
            metrics=metrics,
            factors=factors,
            generated_at=evaluated_at,
            session_label=ctx.session,
            is_expiry_day=ctx.is_expiry_day,
            cluster_scores=cluster_scores,
            regime=regime,
            shadow=ShadowFeatures(
                chain=chain_shadow,
                futures=self._sources.futures.latest(underlying),
                chart=chart_shadow,
            ),
            premarket_action=premarket.recommended_action.value,
            premarket_generated_at=premarket.generated_at,
            premarket_wait_trigger=premarket.wait_trigger.value,
            freshness_diagnostics=freshness_diagnostics,
        )

    async def _spot_tick_for_freshness(self, symbol: str) -> Tick:
        """Angel only — Yahoo fetch-time ticks must not enter the freshness gate."""
        return await self._market_data.get_preferred_tick(symbol)

    async def _optional_indicators_15m(self, symbol: str) -> Optional[IntradayIndicators]:
        if self._sources.indicators_15m is None:
            return None
        try:
            return await self._sources.indicators_15m.get(symbol)
        except Exception:
            return None

    async def _optional_vix(self) -> Optional[IndiaVixSnapshot]:
        if self._sources.vix is None:
            return None
        try:
            return await self._sources.vix.collect()
        except Exception:
            return None

    async def _optional_breadth(self) -> Optional[BreadthSnapshot]:
        try:
            from services.market_data import market_data_service

            raw_breadth = await market_data_service.get_market_breadth()
            return BreadthSnapshot(
                available=True,
                advancing=raw_breadth.get("advancing", 0),
                declining=raw_breadth.get("declining", 0),
                unchanged=raw_breadth.get("unchanged", 0),
                advance_decline_ratio=raw_breadth.get("advance_decline_ratio", 1.0),
                advancing_pct=round(
                    raw_breadth.get("advancing", 0) / max(raw_breadth.get("total", 1), 1) * 100, 1
                ),
                session_label="INTRADAY",
            )
        except Exception:
            return None

    async def _chart_shadow(
        self, symbol: str, indicators: IntradayIndicators, now: datetime
    ) -> ChartStructureFeatures:
        return await self._analyzers.chart_shadow.calculate(
            symbol=symbol,
            session_range=indicators.session_range,
            atr=indicators.atr,
            as_of=now,
        )

    def _suggest(
        self, chain: OptionChain, direction: PredictionDirection, indicators: IntradayIndicators
    ) -> Optional[SuggestedContract]:
        if direction in NON_ACTIONABLE:
            return None
        option_type = OPTION_TYPE_BY_DIRECTION[direction]
        selected = self._analyzers.strikes.select(chain, option_type)
        if selected is None:
            return None
        strike, quote = selected
        return SuggestedContract(
            strike=strike,
            option_type=option_type,
            quote=quote,
            levels=self._analyzers.levels.plan(quote, indicators.atr),
        )
