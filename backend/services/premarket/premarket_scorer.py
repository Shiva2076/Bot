from typing import List, Tuple

from schemas.premarket import MarketSentiment, PremarketFactor, RecommendedAction, VolatilityBand
from schemas.premarket import IndiaVixSnapshot, NiftyOpeningContext


class PremarketScorer:
    def __init__(
        self,
        bullish_threshold: float,
        bearish_threshold: float,
        min_included_factors: int,
        large_gap_pct: float,
    ):
        self._bullish = bullish_threshold
        self._bearish = bearish_threshold
        self._min_included = min_included_factors
        self._large_gap_pct = large_gap_pct

    def score(self, factors: List[PremarketFactor]) -> Tuple[float, float, MarketSentiment, List[str]]:
        included = [f for f in factors if f.included]
        if len(included) < self._min_included:
            return 0.0, 0.0, MarketSentiment.INSUFFICIENT_DATA, ["Too few valid indicators for a directional call."]
        total_weight = sum(f.weight for f in included)
        directional = sum(f.score * f.weight for f in included) / total_weight
        agreement = abs(sum(1 if f.score > 0 else -1 if f.score < 0 else 0 for f in included)) / len(included)
        confidence = min(92.0, round(40.0 + 50.0 * abs(directional) + 20.0 * agreement, 1))
        if directional >= self._bullish:
            sentiment = MarketSentiment.BULLISH
        elif directional <= self._bearish:
            sentiment = MarketSentiment.BEARISH
        else:
            sentiment = MarketSentiment.NEUTRAL
        reasons = [f"{f.name}: {f.detail}" for f in included]
        return round(directional, 3), confidence, sentiment, reasons

    def recommend(
        self,
        sentiment: MarketSentiment,
        confidence: float,
        vix: IndiaVixSnapshot,
        nifty: NiftyOpeningContext,
        conflicting: bool,
    ) -> RecommendedAction:
        if sentiment == MarketSentiment.INSUFFICIENT_DATA:
            return RecommendedAction.NO_TRADE
        if nifty.available and nifty.gap_pct is not None and abs(nifty.gap_pct) >= self._large_gap_pct:
            return RecommendedAction.WAIT
        if vix.available and vix.band == VolatilityBand.HIGH:
            return RecommendedAction.WAIT if confidence >= 55 else RecommendedAction.NO_TRADE
        if conflicting or confidence < 55:
            return RecommendedAction.WAIT
        if sentiment in {MarketSentiment.BULLISH, MarketSentiment.BEARISH} and confidence >= 55:
            return RecommendedAction.WATCH
        return RecommendedAction.WAIT
