from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction
from schemas.trade_decision import (
    TradeDecisionBlockCode,
    TradeDecisionGateDiagnostic,
    TradeDecisionInputs,
    TradeDecisionResponse,
    TradeDecisionStatus,
)
from services.trading.entry_session_gate import PERMITTED_ENTRY_PHASES

REASON_TRADE = "Actionable setup; all safety checks passed"
REASON_WAITING = "Waiting for a confirmed setup"
REASON_PREMARKET_NO_TRADE = "Premarket NO_TRADE: new entries blocked"
REASON_FRESHNESS = "Exchange timestamp missing; freshness unverified"
REASON_SESSION = "Market session closed"
REASON_NO_CONTRACT = "No valid option contract"
REASON_RISK = "Risk limit exceeded"
REASON_SETUP = "No actionable entry setup"
REASON_PREDICTION_UNAVAILABLE = "Prediction unavailable; refresh and retry"

ACTIONABLE_DIRECTIONS = frozenset({PredictionDirection.CALL, PredictionDirection.PUT})
WAITING_GATE_REASONS = frozenset({
    GateReason.PREMARKET_WAIT,
    GateReason.MTF_CONFLICT,
    GateReason.CLUSTER_DISAGREEMENT,
    GateReason.LOW_COVERAGE,
    GateReason.LOW_SIGNAL_SCORE,
    GateReason.EXPIRY_PRE_CLOSE,
    GateReason.INVALID_DATA,
})
FRESHNESS_GATE_REASONS = frozenset({
    GateReason.STALE_DATA,
    GateReason.UNKNOWN_FRESHNESS,
})

# Highest priority first among blocking codes.
BLOCK_PRIORITY = (
    TradeDecisionBlockCode.PREMARKET_NO_TRADE,
    TradeDecisionBlockCode.SESSION_CLOSED,
    TradeDecisionBlockCode.FRESHNESS_UNVERIFIED,
    TradeDecisionBlockCode.WAITING_SETUP,
    TradeDecisionBlockCode.NO_CONTRACT,
    TradeDecisionBlockCode.RISK_LIMIT,
    TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE,
)

REASON_BY_CODE = {
    TradeDecisionBlockCode.PREMARKET_NO_TRADE: REASON_PREMARKET_NO_TRADE,
    TradeDecisionBlockCode.SESSION_CLOSED: REASON_SESSION,
    TradeDecisionBlockCode.FRESHNESS_UNVERIFIED: REASON_FRESHNESS,
    TradeDecisionBlockCode.WAITING_SETUP: REASON_WAITING,
    TradeDecisionBlockCode.NO_CONTRACT: REASON_NO_CONTRACT,
    TradeDecisionBlockCode.RISK_LIMIT: REASON_RISK,
    TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE: REASON_SETUP,
}


def _prediction_missing(inputs: TradeDecisionInputs) -> bool:
    return (
        inputs.prediction_direction is None
        and inputs.gate_reason is None
        and inputs.data_freshness is None
        and not inputs.contract_symbol
    )


class TradeDecisionEvaluator:
    """
    Maps authoritative gate results onto TRADE / NO_TRADE.
    Does not score markets, authorize orders, or accept client overrides.
    """

    def evaluate(self, inputs: TradeDecisionInputs) -> TradeDecisionResponse:
        diagnostics = self._diagnostics(inputs)
        failures = [d for d in diagnostics if not d.passed]
        if not failures:
            return self._response(
                inputs,
                TradeDecisionStatus.TRADE,
                REASON_TRADE,
                None,
                diagnostics,
                manual_override_eligible=False,
            )
        block = min(failures, key=lambda d: BLOCK_PRIORITY.index(d.code)).code
        reason = (
            REASON_PREDICTION_UNAVAILABLE
            if block == TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE and _prediction_missing(inputs)
            else REASON_BY_CODE[block]
        )
        return self._response(
            inputs,
            TradeDecisionStatus.NO_TRADE,
            reason,
            block,
            diagnostics,
            manual_override_eligible=self._override_eligible(inputs, failures),
        )

    def _diagnostics(self, inputs: TradeDecisionInputs) -> list:
        premarket_blocked = (
            not inputs.premarket_available
            or inputs.premarket_action == RecommendedAction.NO_TRADE
        )
        session_ok = (
            inputs.session_permitted
            and inputs.session_phase in PERMITTED_ENTRY_PHASES
            and inputs.gate_reason != GateReason.MARKET_CLOSED
        )
        prediction_missing = _prediction_missing(inputs)
        # Missing prediction is not an exchange-timestamp failure; surface as setup unavailable.
        freshness_ok = True if prediction_missing else self._freshness_ok(inputs)
        waiting = self._waiting(inputs)
        has_contract = (
            True
            if prediction_missing
            else (inputs.contract_symbol is not None and inputs.contract_symbol != "")
        )
        setup_ok = (
            False
            if prediction_missing
            else (
                inputs.prediction_direction in ACTIONABLE_DIRECTIONS
                and inputs.gate_reason == GateReason.NONE
                and not waiting
            )
        )
        return [
            TradeDecisionGateDiagnostic(
                code=TradeDecisionBlockCode.PREMARKET_NO_TRADE,
                passed=not premarket_blocked,
                detail=(
                    "Premarket unavailable"
                    if not inputs.premarket_available
                    else f"Premarket action {inputs.premarket_action.value if inputs.premarket_action else 'unknown'}"
                ),
            ),
            TradeDecisionGateDiagnostic(
                code=TradeDecisionBlockCode.SESSION_CLOSED,
                passed=session_ok,
                detail=(
                    "Prediction gate MARKET_CLOSED"
                    if inputs.gate_reason == GateReason.MARKET_CLOSED
                    else f"Session phase {inputs.session_phase}"
                ),
            ),
            TradeDecisionGateDiagnostic(
                code=TradeDecisionBlockCode.FRESHNESS_UNVERIFIED,
                passed=freshness_ok,
                detail=(
                    f"Freshness {DataFreshness.NOT_EVALUATED.value}"
                    if prediction_missing
                    else (
                        f"Freshness {inputs.data_freshness.value if inputs.data_freshness else 'unknown'}"
                        f"; exchange verified={inputs.exchange_freshness_verified}"
                    )
                ),
            ),
            TradeDecisionGateDiagnostic(
                code=TradeDecisionBlockCode.WAITING_SETUP,
                passed=not waiting,
                detail=self._waiting_detail(inputs),
            ),
            TradeDecisionGateDiagnostic(
                code=TradeDecisionBlockCode.NO_CONTRACT,
                passed=has_contract,
                detail="Contract present" if has_contract else "No suggested contract",
            ),
            TradeDecisionGateDiagnostic(
                code=TradeDecisionBlockCode.RISK_LIMIT,
                passed=inputs.risk_allowed,
                detail="; ".join(inputs.risk_reasons) if inputs.risk_reasons else "Portfolio risk checks clear",
            ),
            TradeDecisionGateDiagnostic(
                code=TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE,
                passed=setup_ok,
                detail=(
                    "Prediction unavailable"
                    if prediction_missing
                    else (
                        f"Direction {inputs.prediction_direction.value if inputs.prediction_direction else 'none'}"
                        f"; gate {inputs.gate_reason.value if inputs.gate_reason else 'none'}"
                    )
                ),
            ),
        ]

    def _freshness_ok(self, inputs: TradeDecisionInputs) -> bool:
        if inputs.gate_reason in FRESHNESS_GATE_REASONS:
            return False
        if inputs.data_freshness != DataFreshness.FRESH:
            return False
        return inputs.exchange_freshness_verified

    def _waiting(self, inputs: TradeDecisionInputs) -> bool:
        if inputs.premarket_action == RecommendedAction.WAIT:
            return True
        if inputs.prediction_direction == PredictionDirection.WAIT:
            return True
        if inputs.gate_reason in WAITING_GATE_REASONS:
            return True
        return False

    def _waiting_detail(self, inputs: TradeDecisionInputs) -> str:
        if inputs.premarket_action == RecommendedAction.WAIT:
            return "Premarket WAIT"
        if inputs.prediction_direction == PredictionDirection.WAIT:
            return "Prediction WAIT"
        if inputs.gate_reason in WAITING_GATE_REASONS:
            return f"Gate {inputs.gate_reason.value}"
        return "Setup confirmed"

    def _override_eligible(self, inputs: TradeDecisionInputs, failures: list) -> bool:
        """WAIT-only soft block may accept a typed reason later; never NO_TRADE or safety failures."""
        if inputs.premarket_action == RecommendedAction.NO_TRADE:
            return False
        if not inputs.premarket_available:
            return False
        hard = {
            TradeDecisionBlockCode.PREMARKET_NO_TRADE,
            TradeDecisionBlockCode.SESSION_CLOSED,
            TradeDecisionBlockCode.FRESHNESS_UNVERIFIED,
            TradeDecisionBlockCode.RISK_LIMIT,
        }
        if any(d.code in hard for d in failures):
            return False
        return any(d.code == TradeDecisionBlockCode.WAITING_SETUP for d in failures)

    def _response(
        self,
        inputs: TradeDecisionInputs,
        status: TradeDecisionStatus,
        reason: str,
        block_code,
        diagnostics: list,
        manual_override_eligible: bool,
    ) -> TradeDecisionResponse:
        override_note = None
        if inputs.open_manual_override:
            override_note = "Manual override accepted for an open paper position"
        freshness = (
            DataFreshness.NOT_EVALUATED
            if _prediction_missing(inputs)
            else inputs.data_freshness
        )
        return TradeDecisionResponse(
            status=status,
            reason=reason,
            block_code=block_code,
            underlying=inputs.underlying,
            expiry=inputs.expiry,
            session_phase=inputs.session_phase,
            premarket_action=inputs.premarket_action,
            prediction_direction=inputs.prediction_direction,
            gate_reason=inputs.gate_reason,
            data_freshness=freshness,
            contract_symbol=inputs.contract_symbol,
            manual_override_eligible=manual_override_eligible,
            override_note=override_note,
            diagnostics=diagnostics,
        )
