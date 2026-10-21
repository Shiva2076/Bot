from fastapi import Depends, APIRouter
from services.auth.api_key_auth import require_api_key
from services.news_aggregator import get_news_with_sentiment
from services.economic_calendar import get_upcoming_events

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/")
async def get_news(symbol: str = None):
    news = await get_news_with_sentiment(symbol)
    return {"news": news, "count": len(news)}


@router.get("/calendar")
async def get_calendar():
    return {"events": get_upcoming_events()}
