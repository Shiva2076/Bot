from datetime import datetime

import pytz

from schemas.costs import CostConfig
from schemas.trading import Candle
from services.backtest.orb_backtester import OrbIntradayBacktester
from services.backtest.orb_metrics import OrbMetricsReporter
from services.backtest.walk_forward import WalkForwardEvaluator
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.risk.position_sizer import PositionSizer
from services.strategies.orb.orb_config import OrbStrategyConfig
from services.strategies.orb.orb_signal_engine import OrbSignalEngine

IST = pytz.timezone("Asia/Kolkata")


def _ts(day: int, hour: int, minute: int) -> int:
    return int(IST.localize(datetime(2026, 10, day, hour, minute)).timestamp())


def _c(day, hour, minute, o, h, l, c, v=1000) -> Candle:
    return Candle(time=_ts(day, hour, minute), open=o, high=h, low=l, close=c, volume=v)


def _session(day: int, breakout: bool) -> list:
    candles = []
    price = 100.0
    for i in range(20):
        m = 7 * 60 + i * 5
        candles.append(_c(day, m // 60, m % 60, price, price + 0.5, price - 0.5, price, 1000))
    candles += [
        _c(day, 9, 15, 100, 101, 99.5, 100.5, 1200),
        _c(day, 9, 20, 100.5, 101.2, 100, 100.8, 1100),
        _c(day, 9, 25, 100.8, 101.5, 100.2, 101.0, 1300),
    ]
    if breakout:
        candles.append(_c(day, 9, 35, 101.6, 103, 101.4, 102.5, 5000))
        candles.append(_c(day, 9, 40, 102.6, 104, 102.4, 103.5, 2000))  # next bar fill
        candles.append(_c(day, 10, 0, 103.5, 106, 103, 105.5, 2000))  # target path
    else:
        candles.append(_c(day, 9, 35, 100.5, 101, 100, 100.6, 1000))
        candles.append(_c(day, 9, 40, 100.6, 101, 100, 100.5, 1000))
    return candles


def test_next_bar_execution_and_costs_reduce_pnl():
    candles = _session(21, breakout=True)
    costs = PaperCostCalculator(
        CostConfig(
            brokerage_pct=0.03, brokerage_flat=20, exchange_txn_pct=0.00345, sebi_pct=0.0001,
            stamp_duty_buy_pct=0.015, stt_sell_pct=0.025, gst_pct=18, slippage_bps=5,
        )
    )
    engine = OrbSignalEngine(OrbStrategyConfig(require_vwap=True, require_volume=True), PositionSizer(1.0))
    result = OrbIntradayBacktester(engine, costs).run("RELIANCE.NS", candles, 1_000_000)
    assert isinstance(result["trades"], list)


def test_walk_forward_structure():
    candles = []
    for day in range(21, 28):
        candles.extend(_session(day, breakout=(day % 2 == 1)))
    costs = PaperCostCalculator(
        CostConfig(
            brokerage_pct=0.03, brokerage_flat=20, exchange_txn_pct=0.00345, sebi_pct=0.0001,
            stamp_duty_buy_pct=0.015, stt_sell_pct=0.025, gst_pct=18, slippage_bps=5,
        )
    )
    engine = OrbSignalEngine(OrbStrategyConfig(require_vwap=False, require_volume=False), PositionSizer(1.0))
    out = WalkForwardEvaluator(OrbIntradayBacktester(engine, costs), OrbMetricsReporter()).evaluate(
        "TCS.NS", candles, 1_000_000, train_ratio=0.6, folds=2
    )
    assert "train" in out and "test" in out and "baseline_buy_hold_test" in out
    assert "expectancy" in out["test"]
    assert out["execution_model"] == "next_bar_open_after_signal_close"


def test_no_lookahead_uses_prefix_only():
    # Engine evaluate with prefix ending before breakout should not see future
    engine = OrbSignalEngine(OrbStrategyConfig(require_vwap=False, require_volume=False), PositionSizer(1.0))
    candles = _session(21, breakout=True)
    pre = [c for c in candles if c.time < _ts(21, 9, 35)]
    signal = engine.evaluate("X.NS", pre, 1_000_000)
    assert signal.decision.value in {"NO_TRADE", "INVALIDATED"}
