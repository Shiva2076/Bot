"""
Risk Agent — evaluates risk per trade and assigns a risk score card.
"""
from typing import Dict, List
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
MAX_SCORE = 12  # Risk agent is inverse — high score = LOW risk = more favorable


def analyze(
    ta: Dict,
    regime: Dict,
    sector_data: Dict,
    economic_events: List[Dict],
    portfolio_heat: float,
    symbol: str,
) -> Dict:
    """
    Evaluate risk conditions for a trade.
    portfolio_heat: % of capital currently deployed (0–100)
    """
    score = MAX_SCORE  # Start at max, deduct for risks
    risk_factors: List[str] = []
    favorable: List[str] = []
    risk_level = "LOW"

    # Market regime modifier
    regime_name = regime.get("regime", "UNKNOWN")
    if regime_name == "BEAR_TRENDING":
        score -= 5
        risk_factors.append("Bearish market regime — elevated risk for longs")
    elif regime_name == "HIGH_VOLATILITY":
        score -= 4
        risk_factors.append("High volatility regime — unpredictable price swings")
    elif regime_name == "BULL_TRENDING":
        score += 2
        favorable.append("Bullish market regime supports trade")
    elif regime_name == "RANGE_BOUND":
        score -= 1

    # VIX level
    vix = regime.get("details", {}).get("vix")
    if vix:
        if vix > 20:
            score -= 3
            risk_factors.append(f"India VIX elevated ({vix:.1f}) — market fearful")
        elif vix < 12:
            score += 2
            favorable.append(f"VIX low ({vix:.1f}) — calm market conditions")

    # Upcoming economic events
    now = datetime.now(IST)
    upcoming_high_impact = [
        e for e in economic_events
        if e.get("impact") == "HIGH" and e.get("hours_away", 999) <= 48
    ]
    if upcoming_high_impact:
        score -= 3
        names = ", ".join(e.get("name", "") for e in upcoming_high_impact[:2])
        risk_factors.append(f"High-impact event within 48h: {names}")

    # Portfolio heat
    if portfolio_heat > 70:
        score -= 3
        risk_factors.append(f"Portfolio already {portfolio_heat:.0f}% deployed — overexposure risk")
    elif portfolio_heat < 40:
        score += 1
        favorable.append("Portfolio has capacity for new positions")

    # Technical risk factors
    if ta:
        sr = ta.get("support_resistance", {})
        price = ta.get("price", 0)
        r1 = sr.get("resistance_1", 0)
        if r1 and price and r1 > 0:
            pct_to_r = (r1 - price) / price * 100
            if pct_to_r < 1.5:
                score -= 2
                risk_factors.append(f"Strong resistance at ₹{r1:.0f} — only {pct_to_r:.1f}% away")

        bb_upper = ta.get("bb_upper", 0)
        if bb_upper and price and price > bb_upper * 0.98:
            score -= 2
            risk_factors.append("Price near upper Bollinger Band — potentially extended")

        vol_ratio = ta.get("volume_ratio", 1.0)
        if vol_ratio > 1.5:
            favorable.append(f"High volume confirmation ({vol_ratio:.1f}x average)")
        elif vol_ratio < 0.5:
            score -= 1
            risk_factors.append("Low volume — weak conviction")

    # Sector strength
    if sector_data:
        avoid = sector_data.get("avoid_sectors", [])
        # We'd need the symbol's sector here — simplified check
        if len(avoid) >= 5:
            score -= 1
            risk_factors.append("Most sectors under pressure today")

    score = max(0, min(score, MAX_SCORE + 2))

    if score >= 10:
        risk_level = "LOW"
    elif score >= 6:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    contribution = round((score / MAX_SCORE) * 10, 1)

    return {
        "agent": "risk",
        "symbol": symbol,
        "signal": "BUY" if risk_level == "LOW" else ("NEUTRAL" if risk_level == "MEDIUM" else "SELL"),
        "score": min(score, MAX_SCORE),
        "max_score": MAX_SCORE,
        "confidence_contribution": contribution,
        "risk_level": risk_level,
        "risk_color": {"LOW": "emerald", "MEDIUM": "amber", "HIGH": "rose"}[risk_level],
        "favorable_conditions": favorable[:4],
        "risk_factors": risk_factors[:4],
        "upcoming_events": upcoming_high_impact[:2],
        "reasons": favorable[:3],
        "warnings": risk_factors[:3],
    }
