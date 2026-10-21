from schemas.costs import CostConfig
from schemas.personal_trade import TradeAction
from services.costs.paper_cost_calculator import PaperCostCalculator


def _calc() -> PaperCostCalculator:
    return PaperCostCalculator(
        CostConfig(
            brokerage_pct=0.03,
            brokerage_flat=20,
            exchange_txn_pct=0.00345,
            sebi_pct=0.0001,
            stamp_duty_buy_pct=0.015,
            stt_sell_pct=0.025,
            gst_pct=18,
            slippage_bps=10,
        )
    )


def test_components_sum_to_total_fees_once():
    leg = _calc().leg_cost(1000, 10, TradeAction.BUY, is_entry=True)
    summed = leg.brokerage + leg.exchange + leg.sebi + leg.stamp + leg.stt + leg.gst
    assert round(summed, 2) == leg.total_fees
    assert leg.stt == 0.0
    assert leg.stamp > 0


def test_sell_leg_has_stt_not_stamp():
    leg = _calc().leg_cost(1000, 10, TradeAction.BUY, is_entry=False)
    assert leg.stt > 0
    assert leg.stamp == 0.0


def test_round_trip_not_double_counting_brokerage():
    rt = _calc().estimate_round_trip(1000, 1010, 10, TradeAction.BUY)
    assert rt.total_fees == round(rt.entry.total_fees + rt.exit.total_fees, 2)
    assert rt.entry.brokerage > 0 and rt.exit.brokerage > 0
    assert rt.total_fees < rt.entry.notional  # sanity


def test_slippage_worsens_buy_entry():
    calc = _calc()
    slipped = calc.slipped_price(1000, TradeAction.BUY, is_entry=True)
    assert slipped > 1000
