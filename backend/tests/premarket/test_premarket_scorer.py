from schemas.premarket import (
    IndiaVixSnapshot,
    MarketSentiment,
    NiftyOpeningContext,
    PremarketFactor,
    RecommendedAction,
    VolatilityBand,
)
from services.premarket.premarket_scorer import PremarketScorer


def _factor(name: str, score: float, included: bool = True) -> PremarketFactor:
    sentiment = MarketSentiment.BULLISH if score > 0 else MarketSentiment.BEARISH if score < 0 else MarketSentiment.NEUTRAL
    return PremarketFactor(
        name=name,
        sentiment=sentiment,
        score=score,
        weight=0.25,
        included=included,
        detail=name,
    )


def test_insufficient_when_too_few_factors():
    scorer = PremarketScorer(0.18, -0.18, min_included_factors=2, large_gap_pct=0.8)
    score, conf, sentiment, _ = scorer.score([_factor("A", 1.0), _factor("B", 1.0, included=False)])
    assert sentiment == MarketSentiment.INSUFFICIENT_DATA
    assert score == 0.0


def test_conflicting_signals_recommend_wait():
    scorer = PremarketScorer(0.18, -0.18, min_included_factors=2, large_gap_pct=0.8)
    action = scorer.recommend(
        sentiment=MarketSentiment.NEUTRAL,
        confidence=50,
        vix=IndiaVixSnapshot(available=True, value=14, band=VolatilityBand.MODERATE),
        nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
        conflicting=True,
    )
    assert action == RecommendedAction.WAIT


def test_large_gap_forces_wait():
    scorer = PremarketScorer(0.18, -0.18, min_included_factors=2, large_gap_pct=0.8)
    action = scorer.recommend(
        sentiment=MarketSentiment.BULLISH,
        confidence=80,
        vix=IndiaVixSnapshot(available=True, value=12, band=VolatilityBand.LOW),
        nifty=NiftyOpeningContext(available=True, gap_pct=1.2),
        conflicting=False,
    )
    assert action == RecommendedAction.WAIT


def test_bullish_score_when_factors_align():
    scorer = PremarketScorer(0.18, -0.18, min_included_factors=2, large_gap_pct=0.8)
    score, conf, sentiment, reasons = scorer.score([
        _factor("Global", 1.0),
        _factor("Breadth", 0.8),
        _factor("Nifty", 0.5),
    ])
    assert sentiment == MarketSentiment.BULLISH
    assert score > 0.18
    assert conf > 50
    assert reasons
