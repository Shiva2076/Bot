"""
Historical Pattern Agent — searches historical data for similar technical setups.
Returns success rate, average gain, and holding period for similar past setups.
"""
import pandas as pd
import numpy as np
from typing import Dict, List
from engines.technical_analysis import compute_rsi, compute_macd, compute_ema

MAX_SCORE = 18


def find_similar_setups(df: pd.DataFrame, current_ta: Dict, lookback_years: int = 5) -> Dict:
    """
    Search historical candles for similar RSI + MACD + EMA setups.
    Returns historical success rate and average return over 5/10/20 days.
    """
    if df is None or len(df) < 100:
        return {"occurrences": 0, "success_rate": 0, "avg_gain_5d": 0}

    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["close"], inplace=True)

    close = df["close"]
    rsi = compute_rsi(close, 14)
    macd = compute_macd(close)
    ema_200 = compute_ema(close, 200)
    ema_50 = compute_ema(close, 50)

    current_rsi = current_ta.get("rsi", 50)
    current_above_200 = current_ta.get("above_ema_200", True)
    current_macd_pos = current_ta.get("macd_histogram", 0) > 0

    # Find matching historical bars (exclude last 20 bars — too recent)
    matches = []
    for i in range(200, len(df) - 20):
        hist_rsi = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50
        hist_above_200 = float(close.iloc[i]) > float(ema_200.iloc[i])
        hist_macd_pos = float(macd["histogram"].iloc[i]) > 0

        rsi_match = abs(hist_rsi - current_rsi) < 10
        ema_match = hist_above_200 == current_above_200
        macd_match = hist_macd_pos == current_macd_pos

        if rsi_match and ema_match and macd_match:
            matches.append(i)

    if not matches:
        return {"occurrences": 0, "success_rate": 50, "avg_gain_5d": 0, "avg_gain_10d": 0}

    # Calculate forward returns
    gains_5d = []
    gains_10d = []
    gains_20d = []
    for idx in matches:
        entry = float(close.iloc[idx])
        if idx + 5 < len(close):
            gains_5d.append((float(close.iloc[idx + 5]) - entry) / entry * 100)
        if idx + 10 < len(close):
            gains_10d.append((float(close.iloc[idx + 10]) - entry) / entry * 100)
        if idx + 20 < len(close):
            gains_20d.append((float(close.iloc[idx + 20]) - entry) / entry * 100)

    wins_5d = sum(1 for g in gains_5d if g > 0)
    success_rate = round(wins_5d / max(len(gains_5d), 1) * 100, 1)

    return {
        "occurrences": len(matches),
        "success_rate": success_rate,
        "avg_gain_5d": round(np.mean(gains_5d), 2) if gains_5d else 0,
        "avg_gain_10d": round(np.mean(gains_10d), 2) if gains_10d else 0,
        "avg_gain_20d": round(np.mean(gains_20d), 2) if gains_20d else 0,
        "avg_holding_days": 7,
    }


def analyze(historical_stats: Dict, symbol: str) -> Dict:
    """Score based on historical pattern success rate."""
    if not historical_stats or historical_stats.get("occurrences", 0) < 10:
        return {
            "agent": "historical_pattern",
            "symbol": symbol,
            "signal": "NEUTRAL",
            "score": 9,
            "max_score": MAX_SCORE,
            "confidence_contribution": 9,
            "historical_stats": historical_stats or {},
            "reasons": ["Insufficient historical data for pattern matching"],
            "warnings": [],
        }

    occurrences = historical_stats.get("occurrences", 0)
    success_rate = historical_stats.get("success_rate", 50)
    avg_gain = historical_stats.get("avg_gain_5d", 0)

    score = 0
    reasons: List[str] = []
    warnings: List[str] = []

    if success_rate >= 70:
        score = MAX_SCORE
        reasons.append(
            f"Similar setup occurred {occurrences} times — {success_rate:.0f}% success rate, "
            f"avg gain +{avg_gain:.1f}%"
        )
    elif success_rate >= 60:
        score = 13
        reasons.append(
            f"Historical analysis: {occurrences} similar setups, {success_rate:.0f}% bullish outcomes"
        )
    elif success_rate >= 50:
        score = 9
        reasons.append(f"Neutral historical pattern ({success_rate:.0f}% win rate in similar setups)")
    else:
        score = 4
        warnings.append(
            f"Historically weak setup — only {success_rate:.0f}% of {occurrences} similar cases were bullish"
        )

    signal = "BUY" if score >= 13 else ("SELL" if score <= 4 else "NEUTRAL")
    contribution = round((score / MAX_SCORE) * 18, 1)

    return {
        "agent": "historical_pattern",
        "symbol": symbol,
        "signal": signal,
        "score": score,
        "max_score": MAX_SCORE,
        "confidence_contribution": contribution,
        "historical_stats": historical_stats,
        "reasons": reasons,
        "warnings": warnings,
    }
