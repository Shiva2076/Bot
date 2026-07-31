"""
Smart Money Concepts (SMC) Engine
Detects: Fair Value Gaps, Order Blocks, Break of Structure, Change of Character, Liquidity Zones
"""
import pandas as pd
import numpy as np
from typing import Dict, List


def detect_fair_value_gaps(df: pd.DataFrame, lookback: int = 50) -> List[Dict]:
    """
    Fair Value Gap: A 3-candle pattern where candle 1 high and candle 3 low don't overlap.
    Bullish FVG: Candle 1 high < Candle 3 low
    Bearish FVG: Candle 1 low > Candle 3 high
    """
    df = df.tail(lookback).reset_index(drop=True)
    fvgs = []
    for i in range(2, len(df)):
        c1_high = df["high"].iloc[i - 2]
        c1_low = df["low"].iloc[i - 2]
        c3_high = df["high"].iloc[i]
        c3_low = df["low"].iloc[i]
        # Bullish FVG
        if c1_high < c3_low:
            fvgs.append({
                "type": "BULLISH",
                "top": round(float(c3_low), 2),
                "bottom": round(float(c1_high), 2),
                "index": i,
                "timestamp": str(df.index[i]) if hasattr(df.index[i], '__str__') else i,
            })
        # Bearish FVG
        elif c1_low > c3_high:
            fvgs.append({
                "type": "BEARISH",
                "top": round(float(c1_low), 2),
                "bottom": round(float(c3_high), 2),
                "index": i,
                "timestamp": str(df.index[i]) if hasattr(df.index[i], '__str__') else i,
            })
    return fvgs[-5:] if fvgs else []


def detect_order_blocks(df: pd.DataFrame, lookback: int = 50) -> List[Dict]:
    """
    Order Block: Last bearish candle before a bullish impulse (bullish OB)
    or last bullish candle before a bearish impulse (bearish OB).
    """
    df = df.tail(lookback).reset_index(drop=True)
    order_blocks = []
    swing_size = 3

    for i in range(swing_size, len(df) - swing_size):
        # Check for bullish move after bearish candle
        candle = df.iloc[i]
        is_bearish = candle["close"] < candle["open"]
        next_candles = df.iloc[i + 1: i + swing_size + 1]
        if is_bearish and len(next_candles) == swing_size:
            impulse = next_candles["close"].iloc[-1] - candle["high"]
            if impulse > 0 and (impulse / candle["high"]) > 0.01:
                order_blocks.append({
                    "type": "BULLISH",
                    "top": round(float(candle["high"]), 2),
                    "bottom": round(float(candle["low"]), 2),
                    "index": i,
                })
        # Check for bearish move after bullish candle
        is_bullish = candle["close"] > candle["open"]
        if is_bullish and len(next_candles) == swing_size:
            impulse = candle["low"] - next_candles["close"].iloc[-1]
            if impulse > 0 and (impulse / candle["low"]) > 0.01:
                order_blocks.append({
                    "type": "BEARISH",
                    "top": round(float(candle["high"]), 2),
                    "bottom": round(float(candle["low"]), 2),
                    "index": i,
                })

    return order_blocks[-4:] if order_blocks else []


def detect_structure_breaks(df: pd.DataFrame, lookback: int = 60) -> Dict:
    """
    Break of Structure (BOS): Price breaks a prior swing high/low in trend direction.
    Change of Character (CHoCH): Price breaks opposite swing — signals reversal.
    """
    df = df.tail(lookback).reset_index(drop=True)
    swing_highs = []
    swing_lows = []
    window = 5

    for i in range(window, len(df) - window):
        if df["high"].iloc[i] == df["high"].iloc[i - window: i + window + 1].max():
            swing_highs.append({"price": round(float(df["high"].iloc[i]), 2), "index": i})
        if df["low"].iloc[i] == df["low"].iloc[i - window: i + window + 1].min():
            swing_lows.append({"price": round(float(df["low"].iloc[i]), 2), "index": i})

    current_price = float(df["close"].iloc[-1])
    bos = None
    choch = None

    if len(swing_highs) >= 2:
        last_high = swing_highs[-1]["price"]
        prev_high = swing_highs[-2]["price"]
        if current_price > last_high:
            if last_high > prev_high:
                bos = {"direction": "BULLISH", "broken_level": last_high, "type": "BOS"}
            else:
                choch = {"direction": "BULLISH_REVERSAL", "broken_level": last_high, "type": "CHoCH"}

    if len(swing_lows) >= 2:
        last_low = swing_lows[-1]["price"]
        prev_low = swing_lows[-2]["price"]
        if current_price < last_low:
            if last_low < prev_low:
                bos = {"direction": "BEARISH", "broken_level": last_low, "type": "BOS"}
            else:
                choch = {"direction": "BEARISH_REVERSAL", "broken_level": last_low, "type": "CHoCH"}

    return {
        "swing_highs": swing_highs[-3:],
        "swing_lows": swing_lows[-3:],
        "bos": bos,
        "choch": choch,
    }


def detect_liquidity_zones(df: pd.DataFrame) -> Dict:
    """
    Liquidity zones sit just above recent swing highs (buy-side liquidity)
    and just below recent swing lows (sell-side liquidity).
    """
    recent = df.tail(100)
    swing_highs = recent["high"].nlargest(5).tolist()
    swing_lows = recent["low"].nsmallest(5).tolist()
    return {
        "buy_side_liquidity": [round(h, 2) for h in swing_highs],
        "sell_side_liquidity": [round(l, 2) for l in swing_lows],
    }


def run_smc_analysis(df: pd.DataFrame) -> Dict:
    """Run all Smart Money Concept analyses and return a combined result."""
    if df is None or len(df) < 20:
        return {}
    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["close", "high", "low", "open"], inplace=True)
    return {
        "fair_value_gaps": detect_fair_value_gaps(df),
        "order_blocks": detect_order_blocks(df),
        "structure": detect_structure_breaks(df),
        "liquidity_zones": detect_liquidity_zones(df),
    }
