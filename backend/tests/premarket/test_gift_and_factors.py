import asyncio
from datetime import datetime, timezone

from schemas.premarket import BreadthSnapshot, GiftNiftySnapshot, IndexMove, MarketSentiment, NiftyOpeningContext
from services.premarket.gift_nifty_provider import GiftNiftyProvider
from services.premarket.premarket_factor_analyzer import PremarketFactorAnalyzer


def test_gift_provider_marks_unavailable():
    snapshot = asyncio.run(GiftNiftyProvider().collect())
    assert snapshot.available is False
    assert snapshot.warning


def test_excluded_gift_does_not_enter_score_weighting():
    analyzer = PremarketFactorAnalyzer(0.2, 0.25, 0.25, 0.2, 0.05, 0.05, 0.8)
    factors, excluded = analyzer.analyze(
        global_markets=[
            IndexMove(
                symbol="^DJI",
                name="Dow",
                last=1,
                change_pct=0.5,
                sentiment=MarketSentiment.BULLISH,
                timestamp=datetime.now(timezone.utc),
                source="TEST",
            )
        ],
        gift=GiftNiftySnapshot(available=False, warning="missing"),
        breadth=BreadthSnapshot(
            available=True,
            advancing=30,
            declining=20,
            unchanged=0,
            advance_decline_ratio=1.5,
            advancing_pct=60,
            session_label="PRIOR",
        ),
        nifty=NiftyOpeningContext(available=True, previous_close=23000, last=23050, gap_pct=0.22),
        news_score=0.1,
        strongest_avg=0.8,
        weakest_avg=-0.4,
    )
    assert "GIFT Nifty" in excluded
    gift = next(f for f in factors if f.name == "GIFT Nifty")
    assert gift.included is False
