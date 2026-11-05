import asyncio
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.trade_repository import TradeRepository
from schemas.options import OptionUnderlying
from schemas.order_entry import OrderSource
from schemas.personal_trade import TradeType
from schemas.prediction import DataFreshness, FreshnessBasis, OptionPrediction
from schemas.premarket import PremarketReport, RecommendedAction
from schemas.trade_decision import TradeDecisionInputs, TradeDecisionResponse
from services.prediction.option_prediction_service import OptionPredictionService
from services.premarket.premarket_analyzer_service import PremarketAnalyzerService
from services.risk.daily_risk_state import DailyRiskState, datetime_today
from services.trading.entry_session_gate import PERMITTED_ENTRY_PHASES, EntrySessionGate
from services.trading.trade_decision_evaluator import TradeDecisionEvaluator

# Keep under the frontend axios default (30s) so the UI gets a fail-closed NO_TRADE
# instead of a client timeout string.
DECISION_COMPONENT_TIMEOUT_SECONDS = 20.0


class TradeDecisionService:
    """Assembles authoritative gate results; evaluation itself does not re-score."""

    def __init__(
        self,
        predictions: OptionPredictionService,
        premarket: PremarketAnalyzerService,
        session_gate: EntrySessionGate,
        evaluator: TradeDecisionEvaluator,
        daily_risk: DailyRiskState,
        max_open_positions: int,
        daily_loss_limit_pct: float,
        starting_capital: float,
    ):
        self._predictions = predictions
        self._premarket = premarket
        self._session_gate = session_gate
        self._evaluator = evaluator
        self._daily_risk = daily_risk
        self._max_open_positions = max_open_positions
        self._daily_loss_limit_pct = daily_loss_limit_pct
        self._starting_capital = starting_capital

    async def evaluate(
        self,
        underlying: OptionUnderlying,
        expiry: date,
        session: AsyncSession,
        force: bool = False,
    ) -> TradeDecisionResponse:
        phase = self._session_gate.current_phase()
        session_permitted = phase in PERMITTED_ENTRY_PHASES
        (premarket_action, premarket_available), prediction = await asyncio.gather(
            self._premarket_state(force),
            self._safe_predict(underlying, expiry, session, force),
        )
        repository = TradeRepository(session)
        risk_allowed, risk_reasons = await self._portfolio_risk(repository)
        open_override = await self._has_open_manual_override(repository)
        return self._evaluator.evaluate(
            TradeDecisionInputs(
                underlying=underlying,
                expiry=expiry,
                session_phase=phase,
                session_permitted=session_permitted,
                premarket_action=premarket_action,
                premarket_available=premarket_available,
                prediction_direction=prediction.direction if prediction else None,
                gate_reason=prediction.gate_reason if prediction else None,
                data_freshness=prediction.data_freshness if prediction else None,
                contract_symbol=self._contract_symbol(prediction),
                exchange_freshness_verified=self._exchange_freshness_verified(prediction),
                risk_allowed=risk_allowed,
                risk_reasons=risk_reasons,
                open_manual_override=open_override,
            )
        )

    async def _premarket_state(self, force: bool) -> Tuple[Optional[RecommendedAction], bool]:
        try:
            report: PremarketReport = await asyncio.wait_for(
                self._premarket.analyze(force=force),
                timeout=DECISION_COMPONENT_TIMEOUT_SECONDS,
            )
            return report.recommended_action, True
        except Exception:
            return None, False

    async def _safe_predict(
        self,
        underlying: OptionUnderlying,
        expiry: date,
        session: AsyncSession,
        force: bool,
    ) -> Optional[OptionPrediction]:
        try:
            return await asyncio.wait_for(
                self._predictions.predict(underlying, expiry, session=session, force=force),
                timeout=DECISION_COMPONENT_TIMEOUT_SECONDS,
            )
        except Exception:
            return None

    async def _portfolio_risk(self, repository: TradeRepository) -> Tuple[bool, List[str]]:
        reasons = []
        if self._daily_risk.kill_switch_active:
            reasons.append("Daily kill switch is active")
        realized = await repository.realized_pnl_on(datetime_today())
        limit = self._starting_capital * (self._daily_loss_limit_pct / 100.0)
        if realized <= -limit:
            reasons.append(f"Daily loss limit breached ({realized:.2f} <= -{limit:.2f})")
        open_count = await repository.count_open()
        if open_count >= self._max_open_positions:
            reasons.append(f"Maximum open positions reached ({self._max_open_positions})")
        return len(reasons) == 0, reasons

    async def _has_open_manual_override(self, repository: TradeRepository) -> bool:
        trades = await repository.list_open(TradeType.MANUAL)
        return any(t.order_source == OrderSource.MANUAL_OVERRIDE.value for t in trades)

    def _contract_symbol(self, prediction: Optional[OptionPrediction]) -> Optional[str]:
        if prediction is None or prediction.contract is None:
            return None
        return prediction.contract.quote.symbol

    def _exchange_freshness_verified(self, prediction: Optional[OptionPrediction]) -> bool:
        if prediction is None:
            return False
        if prediction.data_freshness != DataFreshness.FRESH:
            return False
        if not prediction.quote_timestamps:
            return False
        return all(
            quote.verified is True and quote.basis == FreshnessBasis.EXCHANGE
            for quote in prediction.quote_timestamps
        )
