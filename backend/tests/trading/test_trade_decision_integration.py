"""
HTTP GET /api/trading/decision reflects authoritative evaluator inputs.
Uses dependency injection of a scripted TradeDecisionService.
"""
from datetime import date
import httpx
import pytest
from fastapi import FastAPI

from config import settings
from routers import trading
from schemas.options import OptionUnderlying
from schemas.prediction import DataFreshness, GateReason, PredictionDirection
from schemas.premarket import RecommendedAction
from schemas.trade_decision import TradeDecisionInputs, TradeDecisionStatus
from services.trading.trade_decision_evaluator import REASON_TRADE, REASON_WAITING, TradeDecisionEvaluator

EXPIRY = date(2026, 10, 27)


class ScriptedDecisionService:
    def __init__(self, inputs: TradeDecisionInputs):
        self.inputs = inputs
        self.calls = 0

    async def evaluate(self, underlying, expiry, session, force=False):
        self.calls += 1
        return TradeDecisionEvaluator().evaluate(self.inputs)


def _app(service: ScriptedDecisionService) -> FastAPI:
    app = FastAPI()
    app.include_router(trading.router, prefix='/api/trading')
    trading.trade_decision_service = service
    return app


def _client(service: ScriptedDecisionService) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(service)),
        base_url="http://test",
        headers={"X-API-Key": settings.app_api_key},
    )


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


@pytest.mark.asyncio
async def test_decision_endpoint_returns_trade():
    service = ScriptedDecisionService(_inputs())
    async with _client(service) as client:
        response = await client.get(
            "/api/trading/decision",
            params={"underlying": "NIFTY", "expiry": EXPIRY.isoformat()},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == TradeDecisionStatus.TRADE.value
    assert body["reason"] == REASON_TRADE
    assert "does not authorize" in body["disclaimer"].lower() or "not authorize" in body["disclaimer"].lower()
    assert service.calls == 1


@pytest.mark.asyncio
async def test_decision_endpoint_wait_stays_no_trade():
    service = ScriptedDecisionService(_inputs(premarket_action=RecommendedAction.WAIT))
    async with _client(service) as client:
        response = await client.get(
            "/api/trading/decision",
            params={"underlying": "NIFTY", "expiry": EXPIRY.isoformat()},
        )
    body = response.json()
    assert body["status"] == TradeDecisionStatus.NO_TRADE.value
    assert body["reason"] == REASON_WAITING
    assert body["manual_override_eligible"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides, block",
    [
        ({"premarket_action": RecommendedAction.NO_TRADE}, "PREMARKET_NO_TRADE"),
        ({"session_phase": "POST_CLOSE", "session_permitted": False}, "SESSION_CLOSED"),
        (
            {
                "data_freshness": DataFreshness.UNKNOWN,
                "exchange_freshness_verified": False,
                "gate_reason": GateReason.UNKNOWN_FRESHNESS,
                "contract_symbol": None,
            },
            "FRESHNESS_UNVERIFIED",
        ),
        ({"contract_symbol": None}, "NO_CONTRACT"),
        ({"risk_allowed": False, "risk_reasons": ["Daily kill switch is active"]}, "RISK_LIMIT"),
    ],
)
async def test_decision_endpoint_block_codes(overrides, block):
    service = ScriptedDecisionService(_inputs(**overrides))
    async with _client(service) as client:
        response = await client.get(
            "/api/trading/decision",
            params={"underlying": "NIFTY", "expiry": EXPIRY.isoformat()},
        )
    body = response.json()
    assert body["status"] == "NO_TRADE"
    assert body["block_code"] == block
    assert any(not d["passed"] and d["code"] == block for d in body["diagnostics"])


@pytest.mark.asyncio
async def test_decision_requires_api_key():
    service = ScriptedDecisionService(_inputs())
    async with _client(service) as client:
        response = await client.get(
            "/api/trading/decision",
            params={"underlying": "NIFTY", "expiry": EXPIRY.isoformat()},
            headers={"X-API-Key": "wrong"},
        )
    assert response.status_code == 401
