from datetime import date

import pytest

from schemas.options import OptionUnderlying
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction
from schemas.trade_decision import TradeDecisionBlockCode, TradeDecisionInputs, TradeDecisionStatus
from services.trading.trade_decision_evaluator import (
    REASON_FRESHNESS,
    REASON_NO_CONTRACT,
    REASON_PREDICTION_UNAVAILABLE,
    REASON_PREMARKET_NO_TRADE,
    REASON_RISK,
    REASON_SESSION,
    REASON_TRADE,
    REASON_WAITING,
    TradeDecisionEvaluator,
)

EXPIRY = date(2026, 10, 27)


def _inputs(**overrides) -> TradeDecisionInputs:
    base = dict(
        underlying=OptionUnderlying.NIFTY,
        expiry=EXPIRY,
        session_phase="REGULAR",
        session_permitted=True,
        premarket_action=RecommendedAction.WATCH,
        premarket_available=True,
        prediction_direction=PredictionDirection.CALL,
        gate_reason=GateReason.NONE,
        data_freshness=DataFreshness.FRESH,
        contract_symbol="NIFTY27OCT2625000CE",
        exchange_freshness_verified=True,
        risk_allowed=True,
        risk_reasons=[],
        open_manual_override=False,
    )
    base.update(overrides)
    return TradeDecisionInputs(**base)


@pytest.fixture
def evaluator() -> TradeDecisionEvaluator:
    return TradeDecisionEvaluator()


def test_trade_when_all_gates_pass(evaluator):
    result = evaluator.evaluate(_inputs())
    assert result.status == TradeDecisionStatus.TRADE
    assert result.reason == REASON_TRADE
    assert result.block_code is None
    assert result.manual_override_eligible is False
    assert all(d.passed for d in result.diagnostics)


def test_premarket_no_trade_is_highest_priority(evaluator):
    result = evaluator.evaluate(_inputs(
        premarket_action=RecommendedAction.NO_TRADE,
        session_phase="POST_CLOSE",
        session_permitted=False,
        data_freshness=DataFreshness.UNKNOWN,
        exchange_freshness_verified=False,
        contract_symbol=None,
        risk_allowed=False,
        risk_reasons=["Daily kill switch is active"],
    ))
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.block_code == TradeDecisionBlockCode.PREMARKET_NO_TRADE
    assert result.reason == REASON_PREMARKET_NO_TRADE
    assert result.manual_override_eligible is False


def test_session_closed(evaluator):
    result = evaluator.evaluate(_inputs(session_phase="POST_CLOSE", session_permitted=False))
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.block_code == TradeDecisionBlockCode.SESSION_CLOSED
    assert result.reason == REASON_SESSION


def test_market_closed_gate_maps_to_session(evaluator):
    result = evaluator.evaluate(_inputs(gate_reason=GateReason.MARKET_CLOSED, prediction_direction=PredictionDirection.MARKET_CLOSED))
    assert result.block_code == TradeDecisionBlockCode.SESSION_CLOSED
    assert result.reason == REASON_SESSION


def test_exchange_freshness_unverified(evaluator):
    result = evaluator.evaluate(_inputs(
        data_freshness=DataFreshness.UNKNOWN,
        exchange_freshness_verified=False,
        gate_reason=GateReason.UNKNOWN_FRESHNESS,
        prediction_direction=PredictionDirection.UNKNOWN_FRESHNESS,
        contract_symbol=None,
    ))
    assert result.block_code == TradeDecisionBlockCode.FRESHNESS_UNVERIFIED
    assert result.reason == REASON_FRESHNESS


def test_stale_data_maps_to_freshness(evaluator):
    result = evaluator.evaluate(_inputs(
        data_freshness=DataFreshness.STALE,
        exchange_freshness_verified=False,
        gate_reason=GateReason.STALE_DATA,
        prediction_direction=PredictionDirection.STALE_DATA,
        contract_symbol=None,
    ))
    assert result.block_code == TradeDecisionBlockCode.FRESHNESS_UNVERIFIED
    assert result.reason == REASON_FRESHNESS


def test_waiting_for_setup_under_premarket_wait(evaluator):
    result = evaluator.evaluate(_inputs(premarket_action=RecommendedAction.WAIT))
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.block_code == TradeDecisionBlockCode.WAITING_SETUP
    assert result.reason == REASON_WAITING
    assert result.manual_override_eligible is True


def test_waiting_does_not_become_trade_even_with_contract(evaluator):
    result = evaluator.evaluate(_inputs(
        premarket_action=RecommendedAction.WAIT,
        prediction_direction=PredictionDirection.CALL,
        gate_reason=GateReason.NONE,
        contract_symbol="NIFTY27OCT2625000CE",
    ))
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.reason == REASON_WAITING


def test_prediction_wait_direction(evaluator):
    result = evaluator.evaluate(_inputs(
        prediction_direction=PredictionDirection.WAIT,
        gate_reason=GateReason.LOW_SIGNAL_SCORE,
        contract_symbol=None,
    ))
    assert result.block_code == TradeDecisionBlockCode.WAITING_SETUP
    assert result.reason == REASON_WAITING


def test_no_valid_contract(evaluator):
    result = evaluator.evaluate(_inputs(contract_symbol=None))
    assert result.block_code == TradeDecisionBlockCode.NO_CONTRACT
    assert result.reason == REASON_NO_CONTRACT
    assert result.manual_override_eligible is False


def test_risk_limit_exceeded(evaluator):
    result = evaluator.evaluate(_inputs(
        risk_allowed=False,
        risk_reasons=["Maximum open positions reached (5)"],
    ))
    assert result.block_code == TradeDecisionBlockCode.RISK_LIMIT
    assert result.reason == REASON_RISK
    assert result.manual_override_eligible is False


def test_override_not_eligible_when_safety_fails(evaluator):
    result = evaluator.evaluate(_inputs(
        premarket_action=RecommendedAction.WAIT,
        session_permitted=False,
        session_phase="HOLIDAY_OR_WEEKEND",
    ))
    assert result.manual_override_eligible is False
    assert result.block_code == TradeDecisionBlockCode.SESSION_CLOSED


def test_override_note_only_after_accepted_open_position(evaluator):
    result = evaluator.evaluate(_inputs(open_manual_override=True, premarket_action=RecommendedAction.WAIT))
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.override_note == "Manual override accepted for an open paper position"


def test_diagnostics_expose_secondary_failures(evaluator):
    result = evaluator.evaluate(_inputs(
        session_phase="POST_CLOSE",
        session_permitted=False,
        contract_symbol=None,
        risk_allowed=False,
        risk_reasons=["Daily kill switch is active"],
    ))
    assert result.block_code == TradeDecisionBlockCode.SESSION_CLOSED
    failed = {d.code for d in result.diagnostics if not d.passed}
    assert TradeDecisionBlockCode.SESSION_CLOSED in failed
    assert TradeDecisionBlockCode.NO_CONTRACT in failed
    assert TradeDecisionBlockCode.RISK_LIMIT in failed


def test_premarket_unavailable_blocks_like_no_trade(evaluator):
    result = evaluator.evaluate(_inputs(premarket_available=False, premarket_action=None))
    assert result.block_code == TradeDecisionBlockCode.PREMARKET_NO_TRADE
    assert result.manual_override_eligible is False


def test_missing_prediction_is_not_reported_as_exchange_freshness(evaluator):
    result = evaluator.evaluate(_inputs(
        prediction_direction=None,
        gate_reason=None,
        data_freshness=None,
        contract_symbol=None,
        exchange_freshness_verified=False,
    ))
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.block_code == TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE
    assert result.reason == REASON_PREDICTION_UNAVAILABLE
    assert result.data_freshness == DataFreshness.NOT_EVALUATED
    freshness = next(d for d in result.diagnostics if d.code == TradeDecisionBlockCode.FRESHNESS_UNVERIFIED)
    assert freshness.passed is True
    assert freshness.detail == f"Freshness {DataFreshness.NOT_EVALUATED.value}"


def test_missing_prediction_cannot_be_actionable(evaluator):
    result = evaluator.evaluate(_inputs(
        prediction_direction=None,
        gate_reason=None,
        data_freshness=None,
        contract_symbol=None,
        exchange_freshness_verified=False,
    ))
    assert result.status == TradeDecisionStatus.NO_TRADE
    assert result.status != TradeDecisionStatus.TRADE
    assert result.block_code == TradeDecisionBlockCode.SETUP_NOT_ACTIONABLE
    assert result.data_freshness == DataFreshness.NOT_EVALUATED
    assert result.manual_override_eligible is False
