from datetime import datetime, timedelta, timezone

from schemas.costs import CostConfig
from schemas.personal_trade import TradeAction
from schemas.premarket import RecommendedAction
from schemas.risk import PreTradeOrderContext
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.risk.pre_trade_risk_gate import PreTradeRiskGate


def _gate() -> PreTradeRiskGate:
    return PreTradeRiskGate(
        max_data_age_seconds=30,
        max_risk_per_trade_pct=1.0,
        daily_loss_limit_pct=3.0,
        max_open_positions=5,
        cost_calculator=PaperCostCalculator(
            CostConfig(
                brokerage_pct=0.03,
                brokerage_flat=20,
                exchange_txn_pct=0.00345,
                sebi_pct=0.0001,
                stamp_duty_buy_pct=0.015,
                stt_sell_pct=0.025,
                gst_pct=18,
                slippage_bps=5,
            )
        ),
    )


def _ctx(**overrides) -> PreTradeOrderContext:
    base = dict(
        symbol="RELIANCE.NS",
        action=TradeAction.BUY,
        quantity=10,
        entry_price=1000.0,
        stop_loss=990.0,
        tick_timestamp=datetime.now(timezone.utc),
        tick_provider="TEST",
        open_positions=0,
        starting_capital=1_000_000.0,
        available_cash=1_000_000.0,
        realized_pnl_today=0.0,
        kill_switch_active=False,
        premarket_action=RecommendedAction.WATCH,
        data_warnings=[],
    )
    base.update(overrides)
    return PreTradeOrderContext(**base)


def test_allows_valid_order():
    assert _gate().evaluate(_ctx()).allowed is True


def test_rejects_stale_data():
    decision = _gate().evaluate(_ctx(tick_timestamp=datetime.now(timezone.utc) - timedelta(seconds=120)))
    assert decision.allowed is False
    assert any("stale" in r.lower() for r in decision.reasons)


def test_rejects_premarket_no_trade():
    decision = _gate().evaluate(_ctx(premarket_action=RecommendedAction.NO_TRADE))
    assert decision.allowed is False
    assert any("NO_TRADE" in r for r in decision.reasons)


def test_rejects_kill_switch_and_daily_loss():
    g = _gate()
    assert g.evaluate(_ctx(kill_switch_active=True)).allowed is False
    assert g.evaluate(_ctx(realized_pnl_today=-50_000)).allowed is False


def test_rejects_max_positions_and_oversize_risk():
    g = _gate()
    assert g.evaluate(_ctx(open_positions=5)).allowed is False
    # 1% of 1L = 10k; qty 2000 * 10 stop = 20k risk
    assert g.evaluate(_ctx(quantity=2000, stop_loss=990.0)).allowed is False
