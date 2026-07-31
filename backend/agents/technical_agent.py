"""
Technical Analysis Agent — scores a stock based on technical indicators.
Returns a structured AgentOutput with score, reasons, and warnings.
"""
from typing import Dict, List
from engines.technical_analysis import run_full_analysis
from engines.smart_money import run_smc_analysis


MAX_SCORE = 35


def analyze(ta: Dict, smc: Dict, symbol: str) -> Dict:
    """
    Score the stock based on technical indicators.
    Returns score out of MAX_SCORE.
    """
    score = 0
    reasons: List[str] = []
    warnings: List[str] = []

    if not ta:
        return _empty_output(symbol)

    price = ta.get("price", 0)
    rsi = ta.get("rsi")
    rsi_prev = ta.get("rsi_prev")

    # RSI analysis (0–8 points)
    if rsi is not None:
        if rsi < 30:
            score += 8
            reasons.append(f"RSI extremely oversold ({rsi:.1f}) — strong reversal zone")
        elif rsi < 40:
            score += 6
            reasons.append(f"RSI oversold ({rsi:.1f}) — potential buying opportunity")
        elif rsi < 50:
            score += 3
            reasons.append(f"RSI neutral-to-weak ({rsi:.1f})")
        elif rsi > 70:
            score -= 4
            warnings.append(f"RSI overbought ({rsi:.1f}) — consider waiting for pullback")
        elif rsi > 60:
            score += 2

        # RSI recovering
        if rsi_prev and rsi > rsi_prev and rsi < 50:
            score += 2
            reasons.append("RSI recovering from oversold territory")

    # MACD (0–8 points)
    if ta.get("macd_crossover"):
        score += 8
        reasons.append("MACD bullish crossover — momentum shifting upward")
    elif ta.get("macd_histogram", 0) > 0:
        score += 4
        reasons.append("MACD histogram positive — bullish momentum")
    elif ta.get("macd_crossunder"):
        score -= 5
        warnings.append("MACD bearish crossover — momentum turning negative")

    # EMA position (0–7 points)
    if ta.get("above_ema_200"):
        score += 3
        reasons.append("Price above 200 EMA — long-term bullish trend")
    else:
        warnings.append("Price below 200 EMA — bearish long-term structure")

    if ta.get("above_ema_50"):
        score += 2
        reasons.append("Price above 50 EMA — medium-term bullish")

    if ta.get("above_ema_20"):
        score += 2

    # Supertrend (0–5 points)
    supertrend_dir = ta.get("supertrend_direction", 0)
    if supertrend_dir == 1:
        score += 5
        reasons.append("Supertrend bullish — trending upward")
    elif supertrend_dir == -1:
        score -= 3
        warnings.append("Supertrend bearish — downward trend active")

    # ADX trend strength (0–4 points)
    adx = ta.get("adx", 0)
    if adx > 30:
        score += 4
        reasons.append(f"ADX {adx:.1f} — strong trend in progress")
    elif adx > 20:
        score += 2

    # Volume (0–3 points)
    vol_ratio = ta.get("volume_ratio", 1.0)
    if vol_ratio > 2.0:
        score += 3
        reasons.append(f"Volume {vol_ratio:.1f}x above average — strong conviction")
    elif vol_ratio > 1.3:
        score += 2
        reasons.append(f"Volume above average ({vol_ratio:.1f}x)")
    elif vol_ratio < 0.5:
        warnings.append("Very low volume — weak conviction")

    # SMC signals (bonus)
    if smc:
        structure = smc.get("structure", {})
        if structure.get("bos") and structure["bos"].get("direction") == "BULLISH":
            score += 3
            reasons.append("Bullish Break of Structure (BOS) detected")
        elif structure.get("choch") and "BULLISH" in str(structure.get("choch", {}).get("direction", "")):
            score += 2
            reasons.append("Change of Character (CHoCH) — potential reversal")

        fvgs = smc.get("fair_value_gaps", [])
        bullish_fvgs = [f for f in fvgs if f.get("type") == "BULLISH"]
        if bullish_fvgs:
            reasons.append("Bullish Fair Value Gap present — potential support")

    score = max(0, min(score, MAX_SCORE))
    signal = "BUY" if score >= 20 else ("SELL" if score <= 8 else "NEUTRAL")
    contribution = round((score / MAX_SCORE) * 28, 1)  # max 28% contribution

    return {
        "agent": "technical_analysis",
        "symbol": symbol,
        "signal": signal,
        "score": score,
        "max_score": MAX_SCORE,
        "confidence_contribution": contribution,
        "reasons": reasons[:5],
        "warnings": warnings[:3],
    }


def _empty_output(symbol: str) -> Dict:
    return {
        "agent": "technical_analysis",
        "symbol": symbol,
        "signal": "NEUTRAL",
        "score": 0,
        "max_score": MAX_SCORE,
        "confidence_contribution": 0,
        "reasons": ["Insufficient data"],
        "warnings": [],
    }
