from typing import List, Tuple

from services.economic_calendar import get_events_within_48h
from services.news_aggregator import get_news_with_sentiment


class NewsRiskCollector:
    async def collect(self) -> Tuple[float, List[str], List[str]]:
        news = await get_news_with_sentiment()
        labels = [str(item.get("label", "NEUTRAL")).upper() for item in news[:20]]
        bullish = sum(1 for label in labels if label == "BULLISH")
        bearish = sum(1 for label in labels if label == "BEARISH")
        total = max(len(labels), 1)
        score = (bullish - bearish) / total
        events = [
            f"{event['name']} ({event['date']}, {event['impact']})"
            for event in get_events_within_48h()
        ]
        risks = [f"High-impact event within 48h: {name}" for name in events[:3]]
        if bearish >= 3:
            risks.append(f"News tape skewed bearish ({bearish}/{total} headlines)")
        if bullish >= 3:
            risks.append(f"News tape skewed bullish ({bullish}/{total} headlines)")
        return score, events, risks
