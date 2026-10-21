from datetime import datetime

import pytz

from schemas.trading import Candle
from services.risk.position_sizer import PositionSizer
from services.strategies.orb.orb_config import OrbStrategyConfig
from services.strategies.orb.orb_signal_engine import OrbSignalEngine
from schemas.orb import OrbDecision

IST = pytz.timezone("Asia/Kolkata")


def _ts(hour: int, minute: int) -> int:
    return int(IST.localize(datetime(2026, 10, 21, hour, minute)).timestamp())


def _bar(hour, minute, o, h, l, c, v=1000) -> Candle:
    return Candle(time=_ts(hour, minute), open=o, high=h, low=l, close=c, volume=v)


def test_long_breakout_with_filters():
    # Build enough volume history + opening range then breakout
    candles = []
    price = 100.0
    for i in range(25):
        # prior session-ish bars before open to fill volume MA using same day early bars
        # Use minutes from 7:00 for warm-up then ORB
        pass
    # Warm-up bars 07:00+
    for i in range(20):
        m = 7 * 60 + i * 5
        candles.append(_bar(m // 60, m % 60, price, price + 1, price - 1, price, 1000))
    # Opening range 09:15-09:30
    candles += [
        _bar(9, 15, 100, 101, 99.5, 100.5, 1200),
        _bar(9, 20, 100.5, 101.2, 100, 100.8, 1100),
        _bar(9, 25, 100.8, 101.5, 100.2, 101.0, 1300),
    ]
    # Breakout above 101.5 with strong volume and above VWAP
    candles.append(_bar(9, 35, 101.6, 103, 101.4, 102.5, 5000))
    engine = OrbSignalEngine(
        OrbStrategyConfig(require_vwap=True, require_volume=True, volume_ma_period=20, volume_ma_mult=1.2),
        PositionSizer(1.0),
    )
    signal = engine.evaluate("RELIANCE.NS", candles, 1_000_000)
    assert signal.decision == OrbDecision.LONG
    assert signal.stop_loss == 99.5
    assert signal.entry_price == 102.5
    assert signal.quantity and signal.quantity > 0


def test_no_trade_without_breakout():
    candles = [
        _bar(9, 15, 100, 101, 99, 100, 1000),
        _bar(9, 20, 100, 101, 99, 100, 1000),
        _bar(9, 25, 100, 101, 99, 100, 1000),
        _bar(9, 35, 100, 100.5, 99.5, 100.2, 1000),
    ]
    engine = OrbSignalEngine(OrbStrategyConfig(require_vwap=False, require_volume=False), PositionSizer(1.0))
    signal = engine.evaluate("TCS.NS", candles, 1_000_000)
    assert signal.decision in {OrbDecision.NO_TRADE, OrbDecision.INVALIDATED}
