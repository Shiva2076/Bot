"""
Market Regime Detector
Classifies the current market into one of 5 regimes:
BULL_TRENDING | BEAR_TRENDING | RANGE_BOUND | HIGH_VOLATILITY | LOW_VOLATILITY
"""
import pandas as pd
from typing import Dict
from engines.technical_analysis import compute_ema, compute_atr, compute_adx


REGIME_LABELS = {
    "BULL_TRENDING": {
        "label": "Bull Trending 🐂",
        "color": "emerald",
        "strategy": "Favor longs, momentum plays, breakout entries",
        "confidence_modifier": 1.1,
    },
    "BEAR_TRENDING": {
        "label": "Bear Trending 🐻",
        "color": "rose",
        "strategy": "Avoid longs. Look for shorts or stay in cash.",
        "confidence_modifier": 0.6,
    },
    "RANGE_BOUND": {
        "label": "Range Bound ↔️",
        "color": "amber",
        "strategy": "Buy support, sell resistance. Mean reversion.",
        "confidence_modifier": 0.85,
    },
    "HIGH_VOLATILITY": {
        "label": "High Volatility ⚡",
        "color": "orange",
        "strategy": "Reduce position sizes. Widen stops. Be selective.",
        "confidence_modifier": 0.75,
    },
    "LOW_VOLATILITY": {
        "label": "Low Volatility 😴",
        "color": "sky",
        "strategy": "Trend-following and breakout setups work well.",
        "confidence_modifier": 1.0,
    },
}


def detect_regime(nifty_df: pd.DataFrame, vix_value: float = None) -> Dict:
    """
    Classify current market regime based on NIFTY 50 data.
    Args:
        nifty_df: OHLCV dataframe for ^NSEI
        vix_value: Current India VIX value (optional, fetched separately)
    """
    if nifty_df is None or len(nifty_df) < 50:
        return {"regime": "UNKNOWN", "details": {}}

    df = nifty_df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    close = df["close"]
    current_price = float(close.iloc[-1])

    # EMA 200 for long-term trend
    ema_200 = compute_ema(close, 200)
    ema_50 = compute_ema(close, 50)
    above_ema_200 = current_price > float(ema_200.iloc[-1])
    above_ema_50 = current_price > float(ema_50.iloc[-1])

    # ADX for trend strength
    adx_data = compute_adx(df, period=14)
    adx_value = float(adx_data["adx"].iloc[-1]) if not adx_data["adx"].empty else 20
    plus_di = float(adx_data["plus_di"].iloc[-1])
    minus_di = float(adx_data["minus_di"].iloc[-1])
    strong_trend = adx_value > 25

    # ATR-based volatility
    atr = compute_atr(df, period=14)
    atr_pct = float(atr.iloc[-1]) / current_price * 100
    high_vol = atr_pct > 1.5
    low_vol = atr_pct < 0.5

    # VIX-based volatility override
    if vix_value is not None:
        if vix_value > 20:
            high_vol = True
        elif vix_value < 12:
            low_vol = True

    # 20-day price range to detect ranging markets
    range_20 = df["high"].tail(20).max() - df["low"].tail(20).min()
    range_pct = range_20 / current_price * 100
    ranging = range_pct < 5 and not strong_trend

    # Price momentum (20-day return)
    price_20d_ago = float(close.iloc[-20]) if len(close) >= 20 else current_price
    momentum = (current_price - price_20d_ago) / price_20d_ago * 100

    # Classify regime
    if high_vol:
        regime = "HIGH_VOLATILITY"
    elif low_vol and not strong_trend:
        regime = "LOW_VOLATILITY"
    elif ranging:
        regime = "RANGE_BOUND"
    elif above_ema_200 and strong_trend and plus_di > minus_di:
        regime = "BULL_TRENDING"
    elif not above_ema_200 and strong_trend and minus_di > plus_di:
        regime = "BEAR_TRENDING"
    elif above_ema_200:
        regime = "BULL_TRENDING"
    else:
        regime = "BEAR_TRENDING"

    meta = REGIME_LABELS.get(regime, {})
    return {
        "regime": regime,
        "label": meta.get("label", regime),
        "color": meta.get("color", "gray"),
        "strategy": meta.get("strategy", ""),
        "confidence_modifier": meta.get("confidence_modifier", 1.0),
        "details": {
            "nifty_price": round(current_price, 2),
            "ema_200": round(float(ema_200.iloc[-1]), 2),
            "ema_50": round(float(ema_50.iloc[-1]), 2),
            "above_ema_200": above_ema_200,
            "above_ema_50": above_ema_50,
            "adx": round(adx_value, 2),
            "plus_di": round(plus_di, 2),
            "minus_di": round(minus_di, 2),
            "atr_pct": round(atr_pct, 2),
            "momentum_20d_pct": round(momentum, 2),
            "vix": vix_value,
            "high_volatility": high_vol,
        },
    }
