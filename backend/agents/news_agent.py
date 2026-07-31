"""
News & Sentiment Agent — scores a stock based on news sentiment.
"""
from typing import Dict, List

MAX_SCORE = 20


def analyze(news_items: List[Dict], symbol: str) -> Dict:
    """
    Analyze news sentiment for the given symbol.
    news_items: list of {"title": str, "sentiment": float (-1 to 1), "source": str}
    """
    if not news_items:
        return _empty_output(symbol)

    stock_news = [n for n in news_items if symbol.replace(".NS", "") in n.get("title", "").upper()
                  or symbol.replace(".NS", "") in n.get("related_symbols", [])]

    if not stock_news:
        # Use general market news sentiment
        stock_news = news_items[:10]

    scores = [n.get("compound_score", 0) for n in stock_news]
    avg_score = sum(scores) / len(scores) if scores else 0

    score = 0
    reasons: List[str] = []
    warnings: List[str] = []
    positive_count = sum(1 for s in scores if s > 0.05)
    negative_count = sum(1 for s in scores if s < -0.05)
    total = len(scores)

    if avg_score > 0.3:
        score = 18
        reasons.append(f"Very positive news sentiment ({positive_count}/{total} bullish headlines)")
    elif avg_score > 0.1:
        score = 14
        reasons.append(f"Positive news sentiment ({positive_count}/{total} bullish headlines)")
    elif avg_score > 0:
        score = 10
        reasons.append("Mildly positive news sentiment")
    elif avg_score < -0.3:
        score = 2
        warnings.append(f"Very negative news sentiment ({negative_count}/{total} bearish headlines)")
    elif avg_score < -0.1:
        score = 5
        warnings.append(f"Negative news sentiment ({negative_count}/{total} bearish headlines)")
    else:
        score = 10  # neutral
        reasons.append("News sentiment neutral")

    # Check for specific positive triggers
    positive_triggers = ["quarterly results", "earnings beat", "order win", "acquisition", "buyback",
                         "dividend", "upgrade", "target raised", "revenue growth"]
    negative_triggers = ["downgrade", "miss", "layoffs", "penalty", "sebi", "fraud", "loss",
                         "debt", "downside", "reduce"]

    for item in stock_news[:5]:
        title_lower = item.get("title", "").lower()
        for trigger in positive_triggers:
            if trigger in title_lower:
                score = min(score + 2, MAX_SCORE)
                reasons.append(f"Positive trigger: '{trigger}' in news")
                break
        for trigger in negative_triggers:
            if trigger in title_lower:
                score = max(score - 3, 0)
                warnings.append(f"Caution: '{trigger}' mentioned in news")
                break

    signal = "BUY" if score >= 14 else ("SELL" if score <= 5 else "NEUTRAL")
    contribution = round((score / MAX_SCORE) * 20, 1)

    return {
        "agent": "news_sentiment",
        "symbol": symbol,
        "signal": signal,
        "score": score,
        "max_score": MAX_SCORE,
        "confidence_contribution": contribution,
        "avg_sentiment_score": round(avg_score, 3),
        "news_count": len(stock_news),
        "reasons": list(dict.fromkeys(reasons))[:4],
        "warnings": list(dict.fromkeys(warnings))[:3],
    }


def _empty_output(symbol: str) -> Dict:
    return {
        "agent": "news_sentiment",
        "symbol": symbol,
        "signal": "NEUTRAL",
        "score": 10,
        "max_score": MAX_SCORE,
        "confidence_contribution": 10,
        "avg_sentiment_score": 0,
        "news_count": 0,
        "reasons": ["No recent news found"],
        "warnings": [],
    }
