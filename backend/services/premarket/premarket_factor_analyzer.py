from typing import List, Tuple

from schemas.premarket import (
    BreadthSnapshot,
    GiftNiftySnapshot,
    IndexMove,
    MarketSentiment,
    NiftyOpeningContext,
    PremarketFactor,
)

SENTIMENT_SCORE = {
    MarketSentiment.BULLISH: 1.0,
    MarketSentiment.BEARISH: -1.0,
    MarketSentiment.NEUTRAL: 0.0,
    MarketSentiment.INSUFFICIENT_DATA: 0.0,
}


class PremarketFactorAnalyzer:
    def __init__(
        self,
        global_weight: float,
        gift_weight: float,
        breadth_weight: float,
        nifty_weight: float,
        news_weight: float,
        sector_weight: float,
        large_gap_pct: float,
    ):
        self._global_weight = global_weight
        self._gift_weight = gift_weight
        self._breadth_weight = breadth_weight
        self._nifty_weight = nifty_weight
        self._news_weight = news_weight
        self._sector_weight = sector_weight
        self._large_gap_pct = large_gap_pct

    def analyze(
        self,
        global_markets: List[IndexMove],
        gift: GiftNiftySnapshot,
        breadth: BreadthSnapshot,
        nifty: NiftyOpeningContext,
        news_score: float,
        strongest_avg: float,
        weakest_avg: float,
    ) -> Tuple[List[PremarketFactor], List[str]]:
        factors = [
            self._global(global_markets),
            self._gift(gift),
            self._breadth(breadth),
            self._nifty(nifty),
            self._news(news_score),
            self._sectors(strongest_avg, weakest_avg),
        ]
        excluded = [f.name for f in factors if not f.included]
        return factors, excluded

    def _global(self, markets: List[IndexMove]) -> PremarketFactor:
        if not markets:
            return PremarketFactor(
                name="Global Markets",
                sentiment=MarketSentiment.INSUFFICIENT_DATA,
                score=0.0,
                weight=self._global_weight,
                included=False,
                detail="US/Asia index quotes unavailable.",
            )
        score = sum(SENTIMENT_SCORE[m.sentiment] for m in markets) / len(markets)
        names = ", ".join(f"{m.name} {m.change_pct:+.2f}%" for m in markets[:4])
        return PremarketFactor(
            name="Global Markets",
            sentiment=self._sentiment(score),
            score=round(score, 3),
            weight=self._global_weight,
            included=True,
            detail=names,
        )

    def _gift(self, gift: GiftNiftySnapshot) -> PremarketFactor:
        if not gift.available or gift.change_pct is None:
            return PremarketFactor(
                name="GIFT Nifty",
                sentiment=MarketSentiment.INSUFFICIENT_DATA,
                score=0.0,
                weight=self._gift_weight,
                included=False,
                detail=gift.warning or "GIFT Nifty unavailable.",
            )
        score = max(-1.0, min(1.0, gift.change_pct / 0.4))
        return PremarketFactor(
            name="GIFT Nifty",
            sentiment=gift.sentiment,
            score=round(score, 3),
            weight=self._gift_weight,
            included=True,
            detail=f"GIFT {gift.change_pct:+.2f}% via {gift.source}",
        )

    def _breadth(self, breadth: BreadthSnapshot) -> PremarketFactor:
        if not breadth.available:
            return PremarketFactor(
                name="NSE Breadth",
                sentiment=MarketSentiment.INSUFFICIENT_DATA,
                score=0.0,
                weight=self._breadth_weight,
                included=False,
                detail=breadth.warning or "Breadth unavailable.",
            )
        ratio = breadth.advance_decline_ratio
        if ratio >= 1.5:
            score = 1.0
        elif ratio <= 0.67:
            score = -1.0
        else:
            score = (ratio - 1.0) / 0.5
        return PremarketFactor(
            name="NSE Breadth",
            sentiment=self._sentiment(score),
            score=round(max(-1.0, min(1.0, score)), 3),
            weight=self._breadth_weight,
            included=True,
            detail=(
                f"{breadth.advancing} adv / {breadth.declining} dec "
                f"(A/D {breadth.advance_decline_ratio:.2f}, {breadth.session_label})"
            ),
        )

    def _nifty(self, nifty: NiftyOpeningContext) -> PremarketFactor:
        if not nifty.available or nifty.gap_pct is None:
            return PremarketFactor(
                name="NIFTY Gap / Price",
                sentiment=MarketSentiment.INSUFFICIENT_DATA,
                score=0.0,
                weight=self._nifty_weight,
                included=False,
                detail=nifty.warning or "NIFTY context unavailable.",
            )
        gap = nifty.gap_pct
        if abs(gap) >= self._large_gap_pct:
            score = 0.0
            detail = f"Large gap {gap:+.2f}% — avoid chasing; treat as neutral for direction."
        else:
            score = max(-1.0, min(1.0, gap / 0.35))
            detail = f"Gap {gap:+.2f}% vs prev close {nifty.previous_close}"
        return PremarketFactor(
            name="NIFTY Gap / Price",
            sentiment=self._sentiment(score) if abs(gap) < self._large_gap_pct else MarketSentiment.NEUTRAL,
            score=round(score, 3),
            weight=self._nifty_weight,
            included=True,
            detail=detail,
        )

    def _news(self, news_score: float) -> PremarketFactor:
        return PremarketFactor(
            name="Overnight News",
            sentiment=self._sentiment(news_score),
            score=round(max(-1.0, min(1.0, news_score)), 3),
            weight=self._news_weight,
            included=True,
            detail=f"Headline sentiment balance score {news_score:+.2f}",
        )

    def _sectors(self, strongest_avg: float, weakest_avg: float) -> PremarketFactor:
        spread = strongest_avg - abs(min(weakest_avg, 0.0))
        score = max(-1.0, min(1.0, (strongest_avg + weakest_avg) / 2.0 / 0.8))
        return PremarketFactor(
            name="Sector Rotation",
            sentiment=self._sentiment(score),
            score=round(score, 3),
            weight=self._sector_weight,
            included=True,
            detail=f"Leaders avg {strongest_avg:+.2f}% / laggards avg {weakest_avg:+.2f}% (spread {spread:+.2f})",
        )

    @staticmethod
    def _sentiment(score: float) -> MarketSentiment:
        if score >= 0.2:
            return MarketSentiment.BULLISH
        if score <= -0.2:
            return MarketSentiment.BEARISH
        return MarketSentiment.NEUTRAL
