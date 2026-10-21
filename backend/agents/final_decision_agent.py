"""
Final Decision Agent — synthesizes all 5 agent outputs into a single recommendation.
Generates the confidence breakdown, Why Not Buy caution list, and final signal.
"""
from typing import Dict, List


def synthesize(
    tech_out: Dict,
    news_out: Dict,
    hist_out: Dict,
    inst_out: Dict,
    risk_out: Dict,
    regime: Dict,
    ta: Dict,
    symbol: str,
) -> Dict:
    """
    Combine all agent outputs into a final trade recommendation.
    """
    agents = [tech_out, news_out, hist_out, inst_out, risk_out]

    # --- Confidence Breakdown ---
    breakdown = [
        {
            "label": "Technical Analysis",
            "agent": "technical_analysis",
            "score": tech_out.get("confidence_contribution", 0),
            "max": 28,
            "reasons": tech_out.get("reasons", []),
        },
        {
            "label": "News Sentiment",
            "agent": "news_sentiment",
            "score": news_out.get("confidence_contribution", 0),
            "max": 20,
            "reasons": news_out.get("reasons", []),
        },
        {
            "label": "Historical Pattern",
            "agent": "historical_pattern",
            "score": hist_out.get("confidence_contribution", 0),
            "max": 18,
            "reasons": hist_out.get("reasons", []),
        },
        {
            "label": "Institutional Activity",
            "agent": "institutional",
            "score": inst_out.get("confidence_contribution", 0),
            "max": 12 if inst_out.get("available", True) else 0,
            "reasons": inst_out.get("reasons", []),
        },
        {
            "label": "Risk Assessment",
            "agent": "risk",
            "score": risk_out.get("confidence_contribution", 0),
            "max": 10,
            "reasons": risk_out.get("reasons", []),
        },
    ]

    total_score = sum(b["score"] for b in breakdown)
    total_max = sum(b["max"] for b in breakdown)
    raw_confidence = (total_score / total_max * 100) if total_max else 0

    # Apply regime modifier
    regime_modifier = regime.get("confidence_modifier", 1.0)
    confidence = min(95, max(5, raw_confidence * regime_modifier))

    # Count bullish vs bearish signals
    bullish = sum(1 for a in agents if a.get("signal") == "BUY")
    bearish = sum(1 for a in agents if a.get("signal") == "SELL")

    # Final action
    if bullish >= 3 and confidence >= 55:
        action = "BUY"
    elif bearish >= 3 or confidence <= 35:
        action = "SELL"
    else:
        action = "NEUTRAL"

    # Override if in bear market
    if regime.get("regime") == "BEAR_TRENDING":
        if action == "BUY" and confidence < 75:
            action = "NEUTRAL"

    # --- Entry / SL / Targets ---
    price = ta.get("price", 0) if ta else 0
    atr = ta.get("atr", price * 0.015 if price else 0)
    entry = round(price, 2) if price else 0
    stop_loss = round(price - atr * 1.5, 2) if price and atr else None
    target_1 = round(price + atr * 2.5, 2) if price and atr else None
    target_2 = round(price + atr * 4.0, 2) if price and atr else None

    # --- Why Not Buy caution list ---
    cautions: List[str] = []
    for agent in agents:
        cautions.extend(agent.get("warnings", []))

    regime_name = regime.get("regime", "")
    if regime_name == "HIGH_VOLATILITY":
        cautions.append("High market volatility — reduce position size")
    if regime_name == "BEAR_TRENDING":
        cautions.append("Bear market regime — longs have higher failure rate")

    # SR caution
    if ta:
        sr = ta.get("support_resistance", {})
        r1 = sr.get("resistance_1")
        if r1 and price and (r1 - price) / price * 100 < 2:
            cautions.append(f"Strong resistance nearby at ₹{r1:.0f}")

    # Flatten and stringify to prevent unhashable type list error
    safe_cautions = []
    for c in cautions:
        if isinstance(c, list):
            safe_cautions.extend([str(x) for x in c])
        elif c:
            safe_cautions.append(str(c))
    cautions = list(dict.fromkeys(safe_cautions))[:5]

    # Wait for condition
    wait_for = None
    if action == "NEUTRAL" and ta:
        sr = ta.get("support_resistance", {})
        r1 = sr.get("resistance_1")
        if r1:
            wait_for = f"Breakout and close above ₹{r1:.0f} with volume"
        else:
            wait_for = "RSI confirmation above 40 with MACD crossover"

    # Aggregate all reasons safely
    all_reasons: List[str] = []
    for a in agents:
        raw_reasons = a.get("reasons", [])
        if isinstance(raw_reasons, list):
            for r in raw_reasons:
                if isinstance(r, list):
                    all_reasons.extend([str(x) for x in r if x])
                elif r:
                    all_reasons.append(str(r))
        elif raw_reasons:
            all_reasons.append(str(raw_reasons))
    
    all_reasons = list(dict.fromkeys(all_reasons))[:8]

    return {
        "symbol": symbol,
        "action": action,
        "confidence": round(confidence, 1),
        "entry": entry,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk_level": risk_out.get("risk_level", "MEDIUM"),
        "risk_color": risk_out.get("risk_color", "amber"),
        "confidence_breakdown": breakdown,
        "reasons": all_reasons,
        "cautions": cautions,
        "wait_for": wait_for,
        "market_regime": regime.get("label", "Unknown"),
        "regime_strategy": regime.get("strategy", ""),
        "agent_signals": {
            "technical": tech_out.get("signal"),
            "news": news_out.get("signal"),
            "historical": hist_out.get("signal"),
            "institutional": inst_out.get("signal"),
            "risk": risk_out.get("signal"),
        },
        "historical_stats": hist_out.get("historical_stats", {}),
        "bullish_agents": bullish,
        "bearish_agents": bearish,
    }
