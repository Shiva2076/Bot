from schemas.premarket import MarketSentiment


class SentimentClassifier:
    def __init__(self, bullish_threshold_pct: float, bearish_threshold_pct: float):
        self._bullish = bullish_threshold_pct
        self._bearish = bearish_threshold_pct

    def from_change_pct(self, change_pct: float) -> MarketSentiment:
        if change_pct >= self._bullish:
            return MarketSentiment.BULLISH
        if change_pct <= self._bearish:
            return MarketSentiment.BEARISH
        return MarketSentiment.NEUTRAL
