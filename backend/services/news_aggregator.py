"""
News Aggregator Service — fetches financial news from Indian RSS feeds
and scores sentiment using VADER.
"""
import asyncio
import feedparser
import aiohttp
from typing import List, Dict
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from datetime import datetime, timezone
import re

analyzer = SentimentIntensityAnalyzer()

RSS_FEEDS = [
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "source": "Economic Times"},
    {"url": "https://www.moneycontrol.com/rss/business.xml", "source": "Moneycontrol"},
    {"url": "https://www.livemint.com/rss/markets", "source": "Livemint"},
    {"url": "https://www.business-standard.com/rss/markets-106.rss", "source": "Business Standard"},
    {"url": "https://feeds.feedburner.com/ndtvprofit-latest", "source": "NDTV Profit"},
]

NIFTY50_NAMES = [
    "Reliance", "TCS", "HDFC", "Infosys", "ICICI", "Hindustan Unilever", "ITC",
    "SBI", "Bharti Airtel", "Kotak", "Larsen", "Axis Bank", "Bajaj Finance",
    "Wipro", "Maruti", "HCL", "Sun Pharma", "Tata Motors", "UltraTech",
    "Titan", "Nestle", "Tech Mahindra", "Mahindra", "Asian Paints", "Power Grid",
    "NTPC", "ONGC", "JSW Steel", "Tata Steel", "Hindalco", "Adani", "Cipla",
    "Dr Reddy", "Divi", "Eicher", "Bajaj Auto", "Hero MotoCorp", "Grasim",
    "IndusInd", "BPCL", "Coal India", "UPL", "SBI Life", "HDFC Life", "Apollo",
    "Britannia", "Tata Consumer",
]


def _extract_related_symbols(text: str) -> List[str]:
    """Find stock names mentioned in the text."""
    found = []
    for name in NIFTY50_NAMES:
        if name.lower() in text.lower():
            found.append(name.upper())
    return found[:5]


def _score_sentiment(text: str) -> Dict:
    scores = analyzer.polarity_scores(text)
    return {
        "compound_score": round(scores["compound"], 3),
        "positive": round(scores["pos"], 3),
        "negative": round(scores["neg"], 3),
        "neutral": round(scores["neu"], 3),
        "label": "POSITIVE" if scores["compound"] > 0.05 else (
            "NEGATIVE" if scores["compound"] < -0.05 else "NEUTRAL"
        ),
    }


async def _fetch_feed(session: aiohttp.ClientSession, feed_info: Dict) -> List[Dict]:
    """Fetch and parse a single RSS feed."""
    try:
        async with session.get(feed_info["url"], timeout=aiohttp.ClientTimeout(total=8)) as resp:
            content = await resp.text()
        parsed = feedparser.parse(content)
        items = []
        for entry in parsed.entries[:15]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            full_text = f"{title} {summary}"
            sentiment = _score_sentiment(full_text)
            related = _extract_related_symbols(full_text)
            items.append({
                "title": title,
                "summary": summary[:300] if summary else "",
                "link": entry.get("link", ""),
                "source": feed_info["source"],
                "published": entry.get("published", ""),
                "related_symbols": related,
                **sentiment,
            })
        return items
    except Exception as e:
        print(f"Feed error ({feed_info['source']}): {e}")
        return []


async def get_news_with_sentiment(symbol: str = None) -> List[Dict]:
    """Fetch news from all feeds and return with VADER sentiment scores."""
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_feed(session, feed) for feed in RSS_FEEDS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_news = []
    for result in results:
        if isinstance(result, list):
            all_news.extend(result)

    # Sort by compound score relevance
    all_news.sort(key=lambda x: abs(x.get("compound_score", 0)), reverse=True)

    if symbol:
        stock_name = symbol.replace(".NS", "").replace(".BO", "")
        relevant = [n for n in all_news if stock_name in n.get("title", "").upper()
                    or stock_name in [s.upper() for s in n.get("related_symbols", [])]]
        return relevant if relevant else all_news[:20]

    return all_news[:50]
