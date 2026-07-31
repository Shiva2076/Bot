"""
Institutional Activity Agent — scores based on FII/DII flows, delivery %, OI.
"""
from typing import Dict, List

MAX_SCORE = 15


def analyze(institutional_data: Dict, symbol: str) -> Dict:
    """
    Score based on institutional buying/selling patterns.
    institutional_data: {
        "fii_net": float (positive = buying),
        "dii_net": float,
        "delivery_pct": float (0–100),
        "oi_change_pct": float,
        "pcr": float (put-call ratio)
    }
    """
    if not institutional_data:
        return _empty_output(symbol)

    score = 0
    reasons: List[str] = []
    warnings: List[str] = []

    fii_net = institutional_data.get("fii_net", 0)
    dii_net = institutional_data.get("dii_net", 0)
    delivery_pct = institutional_data.get("delivery_pct", 40)
    oi_change_pct = institutional_data.get("oi_change_pct", 0)
    pcr = institutional_data.get("pcr", 1.0)

    # FII activity (0–5 points)
    if fii_net > 2000:  # Crores
        score += 5
        reasons.append(f"Heavy FII buying (₹{fii_net/100:.0f}Cr net) — institutional accumulation")
    elif fii_net > 500:
        score += 3
        reasons.append(f"FII net buying (₹{fii_net/100:.0f}Cr)")
    elif fii_net < -2000:
        score -= 3
        warnings.append(f"Heavy FII selling (₹{abs(fii_net)/100:.0f}Cr net outflow)")
    elif fii_net < -500:
        score -= 1
        warnings.append(f"FII net selling — institutional caution")

    # DII activity (0–3 points)
    if dii_net > 1000:
        score += 3
        reasons.append(f"DII buying (₹{dii_net/100:.0f}Cr) — domestic institutions supporting")
    elif dii_net > 200:
        score += 2
    elif dii_net < -1000:
        score -= 1
        warnings.append("DII selling along with FII — bearish")

    # Delivery percentage (0–4 points)
    if delivery_pct > 65:
        score += 4
        reasons.append(f"High delivery % ({delivery_pct:.0f}%) — genuine buying interest")
    elif delivery_pct > 50:
        score += 2
        reasons.append(f"Above-average delivery ({delivery_pct:.0f}%)")
    elif delivery_pct < 25:
        warnings.append(f"Low delivery % ({delivery_pct:.0f}%) — speculative activity")

    # OI analysis (0–2 points)
    if oi_change_pct > 5:
        score += 2
        reasons.append(f"OI rising +{oi_change_pct:.1f}% with price — trend continuation")
    elif oi_change_pct < -5:
        warnings.append(f"OI falling {oi_change_pct:.1f}% — positions being closed")

    # PCR (Put-Call Ratio) — 0–3 points
    if pcr > 1.2:
        score += 3
        reasons.append(f"PCR {pcr:.2f} — bearish sentiment, contrarian bullish")
    elif pcr < 0.7:
        score -= 2
        warnings.append(f"PCR {pcr:.2f} — excessive call buying, market may correct")

    score = max(0, min(score, MAX_SCORE))
    signal = "BUY" if score >= 10 else ("SELL" if score <= 4 else "NEUTRAL")
    contribution = round((score / MAX_SCORE) * 12, 1)

    return {
        "agent": "institutional",
        "symbol": symbol,
        "signal": signal,
        "score": score,
        "max_score": MAX_SCORE,
        "confidence_contribution": contribution,
        "reasons": reasons[:4],
        "warnings": warnings[:3],
        "data": institutional_data,
    }


def _empty_output(symbol: str) -> Dict:
    return {
        "agent": "institutional",
        "symbol": symbol,
        "signal": "NEUTRAL",
        "score": 7,
        "max_score": MAX_SCORE,
        "confidence_contribution": 5,
        "reasons": ["Institutional data unavailable"],
        "warnings": [],
        "data": {},
    }
