"""
Institutional Activity Agent — scores based on FII/DII flows, delivery %, OI.
Upgraded with FII index futures positioning and OI buildup interpretation.
"""
from typing import Dict, List, Optional

MAX_SCORE = 20  # raised from 15 to accommodate new dimensions


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
    if not institutional_data or not institutional_data.get("available", False):
        return _empty_output(symbol, institutional_data.get("reason") if institutional_data else None)

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

    # FII Index Futures net (0–4 points)
    fii_futures_net = institutional_data.get("fii_index_futures_net")
    if fii_futures_net is not None:
        if fii_futures_net > 5000:  # contracts
            score += 4
            reasons.append(f"FII index futures net LONG ({fii_futures_net:,.0f} contracts) — institutional directional bet")
        elif fii_futures_net > 1000:
            score += 2
            reasons.append(f"FII index futures mildly long ({fii_futures_net:,.0f} contracts)")
        elif fii_futures_net < -5000:
            score -= 3
            warnings.append(f"FII index futures net SHORT ({abs(fii_futures_net):,.0f} contracts) — institutional hedging")
        elif fii_futures_net < -1000:
            score -= 1
            warnings.append(f"FII index futures mildly short ({abs(fii_futures_net):,.0f} contracts)")

    # OI buildup type from option chain dynamics (0–2 points)
    oi_buildup = institutional_data.get("oi_interpretation", "")
    buildup_map = {
        "CALL_BUILDUP_PUT_UNWINDING": (2, "Call buildup + put unwinding — strong bullish positioning"),
        "CALL_LONG_BUILDUP": (1, "Fresh call OI added — directional bullish bet"),
        "PUT_BUILDUP_CALL_UNWINDING": (-2, "Put buildup + call unwinding — strong bearish positioning"),
        "PUT_LONG_BUILDUP": (-1, "Fresh put OI added — directional bearish bet"),
        "CALL_SHORT_COVERING": (1, "Call short covering — shorts exiting, mild bullish"),
        "PUT_SHORT_COVERING": (-1, "Put short covering — put shorts exiting, mild bearish"),
    }
    if oi_buildup in buildup_map:
        pts, reason_text = buildup_map[oi_buildup]
        if pts > 0:
            score += pts
            reasons.append(reason_text)
        elif pts < 0:
            score += pts  # negative
            warnings.append(reason_text)
    # PCR (Put-Call Ratio) — 0–3 points
    if pcr > 1.2:
        score += 3
        reasons.append(f"PCR {pcr:.2f} — bearish sentiment, contrarian bullish")
    elif pcr < 0.7:
        score -= 2
        warnings.append(f"PCR {pcr:.2f} — excessive call buying, market may correct")

    score = max(0, min(score, MAX_SCORE))
    signal = "BUY" if score >= 14 else ("SELL" if score <= 5 else "NEUTRAL")
    contribution = round((score / MAX_SCORE) * 12, 1)

    return {
        "agent": "institutional",
        "symbol": symbol,
        "signal": signal,
        "score": score,
        "max_score": MAX_SCORE,
        "confidence_contribution": contribution,
        "reasons": reasons[:6],
        "warnings": warnings[:4],
        "data": institutional_data,
    }


def _empty_output(symbol: str, reason: Optional[str]) -> Dict:
    return {
        "agent": "institutional",
        "symbol": symbol,
        "available": False,
        "signal": "NEUTRAL",
        "score": 0,
        "max_score": MAX_SCORE,
        "confidence_contribution": 0,
        "reasons": [f"Institutional data unavailable ({reason or 'no data'}) — excluded from confidence"],
        "warnings": [],
        "data": {},
    }
