from schemas.premarket import (
    IndiaVixSnapshot,
    MarketSentiment,
    NiftyOpeningContext,
    PremarketFactor,
    RecommendedAction,
    VolatilityBand,
)
from schemas.premarket_wait_trigger import PremarketWaitTrigger
from services.premarket.premarket_scorer import PremarketRecommendation, PremarketScorer


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


def _scorer() -> PremarketScorer:
    return PremarketScorer(0.18, -0.18, min_included_factors=2, large_gap_pct=0.8)


def test_insufficient_when_too_few_factors():
    score, conf, sentiment, _ = _scorer().score([_factor("A", 1.0), _factor("B", 1.0, included=False)])
    assert sentiment == MarketSentiment.INSUFFICIENT_DATA
    assert score == 0.0


def test_conflicting_signals_recommend_wait():
    recommendation = _scorer().recommend(
        sentiment=MarketSentiment.NEUTRAL,
        confidence=50,
        vix=IndiaVixSnapshot(available=True, value=14, band=VolatilityBand.MODERATE),
        nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
        conflicting=True,
    )
    assert recommendation.action == RecommendedAction.WAIT
    assert recommendation.wait_trigger == PremarketWaitTrigger.CONFLICT


def test_large_gap_forces_wait():
    recommendation = _scorer().recommend(
        sentiment=MarketSentiment.BULLISH,
        confidence=80,
        vix=IndiaVixSnapshot(available=True, value=12, band=VolatilityBand.LOW),
        nifty=NiftyOpeningContext(available=True, gap_pct=1.2),
        conflicting=False,
    )
    assert recommendation.action == RecommendedAction.WAIT
    assert recommendation.wait_trigger == PremarketWaitTrigger.LARGE_GAP


def test_bullish_score_when_factors_align():
    score, conf, sentiment, reasons = _scorer().score([
        _factor("Global", 1.0),
        _factor("Breadth", 0.8),
        _factor("Nifty", 0.5),
    ])
    assert sentiment == MarketSentiment.BULLISH
    assert score > 0.18
    assert conf > 50
    assert reasons


def test_recommend_actions_unchanged_for_current_inputs():
    """Action identity lock: trigger is additive; actions must match prior recommend() branches."""
    cases = [
        (
            dict(
                sentiment=MarketSentiment.INSUFFICIENT_DATA,
                confidence=0,
                vix=IndiaVixSnapshot(available=False),
                nifty=NiftyOpeningContext(available=False),
                conflicting=False,
            ),
            RecommendedAction.NO_TRADE,
            PremarketWaitTrigger.NONE,
        ),
        (
            dict(
                sentiment=MarketSentiment.BULLISH,
                confidence=80,
                vix=IndiaVixSnapshot(available=True, value=12, band=VolatilityBand.LOW),
                nifty=NiftyOpeningContext(available=True, gap_pct=1.2),
                conflicting=False,
            ),
            RecommendedAction.WAIT,
            PremarketWaitTrigger.LARGE_GAP,
        ),
        (
            dict(
                sentiment=MarketSentiment.BULLISH,
                confidence=80,
                vix=IndiaVixSnapshot(available=True, value=19, band=VolatilityBand.HIGH),
                nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
                conflicting=False,
            ),
            RecommendedAction.WAIT,
            PremarketWaitTrigger.HIGH_VIX,
        ),
        (
            dict(
                sentiment=MarketSentiment.BULLISH,
                confidence=50,
                vix=IndiaVixSnapshot(available=True, value=19, band=VolatilityBand.HIGH),
                nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
                conflicting=False,
            ),
            RecommendedAction.NO_TRADE,
            PremarketWaitTrigger.HIGH_VIX,
        ),
        (
            dict(
                sentiment=MarketSentiment.NEUTRAL,
                confidence=50,
                vix=IndiaVixSnapshot(available=True, value=14, band=VolatilityBand.MODERATE),
                nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
                conflicting=True,
            ),
            RecommendedAction.WAIT,
            PremarketWaitTrigger.CONFLICT,
        ),
        (
            dict(
                sentiment=MarketSentiment.BULLISH,
                confidence=50,
                vix=IndiaVixSnapshot(available=True, value=14, band=VolatilityBand.MODERATE),
                nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
                conflicting=False,
            ),
            RecommendedAction.WAIT,
            PremarketWaitTrigger.LOW_CONFIDENCE,
        ),
        (
            dict(
                sentiment=MarketSentiment.BULLISH,
                confidence=80,
                vix=IndiaVixSnapshot(available=True, value=14, band=VolatilityBand.MODERATE),
                nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
                conflicting=False,
            ),
            RecommendedAction.WATCH,
            PremarketWaitTrigger.NONE,
        ),
        (
            dict(
                sentiment=MarketSentiment.NEUTRAL,
                confidence=80,
                vix=IndiaVixSnapshot(available=True, value=14, band=VolatilityBand.MODERATE),
                nifty=NiftyOpeningContext(available=True, gap_pct=0.1),
                conflicting=False,
            ),
            RecommendedAction.WAIT,
            PremarketWaitTrigger.DEFAULT,
        ),
    ]
    scorer = _scorer()
    for kwargs, action, trigger in cases:
        result = scorer.recommend(**kwargs)
        assert isinstance(result, PremarketRecommendation)
        assert result.action == action
        assert result.wait_trigger == trigger
