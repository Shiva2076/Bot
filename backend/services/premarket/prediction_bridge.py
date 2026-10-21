from datetime import datetime, time as dtime
from typing import List, Optional

import pytz
from pydantic import BaseModel, ConfigDict

from schemas.prediction import FactorCluster, PredictionFactor
from schemas.premarket import MarketSentiment, PremarketReport, RecommendedAction, VolatilityBand
from services.premarket.premarket_analyzer_service import PremarketAnalyzerService
from services.prediction.factor_builder import PredictionFactorBuilder

IST = pytz.timezone("Asia/Kolkata")
PREMARKET_WEIGHT = 0.22
SENTIMENT_TO_SCORE = {
    MarketSentiment.BULLISH: 1.0,
    MarketSentiment.BEARISH: -1.0,
    MarketSentiment.NEUTRAL: 0.0,
    MarketSentiment.INSUFFICIENT_DATA: 0.0,
}
_OPEN = dtime(9, 15)
_FULL_UNTIL = dtime(9, 45)
_ZERO_AFTER = dtime(11, 30)


class PremarketFactorBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    factors: List[PredictionFactor]
    recommended_action: RecommendedAction


class PremarketPredictionBridge:
    """Maps the pre-market report into option-prediction factors with intraday weight decay."""

    def __init__(self, analyzer: PremarketAnalyzerService, builder: PredictionFactorBuilder):
        self._analyzer = analyzer
        self._builder = builder

    async def bundle(self, now: Optional[datetime] = None) -> PremarketFactorBundle:
        report = await self._analyzer.analyze()
        if report.overall_sentiment == MarketSentiment.INSUFFICIENT_DATA:
            return PremarketFactorBundle(
                factors=[
                    self._builder.unavailable(
                        name="Pre-Market Bias",
                        detail="Pre-market report has insufficient data",
                        cluster=FactorCluster.CONTEXT,
                    )
                ],
                recommended_action=report.recommended_action,
            )
        score = SENTIMENT_TO_SCORE[report.overall_sentiment]
        if report.india_vix.available and report.india_vix.band == VolatilityBand.HIGH:
            score *= 0.6
        if report.recommended_action in (RecommendedAction.WAIT, RecommendedAction.NO_TRADE):
            score = 0.0
        decay = self._intraday_decay(now or datetime.now(IST))
        weight = PREMARKET_WEIGHT * decay
        detail = (
            f"Pre-market {report.overall_sentiment.value} "
            f"(heuristic {report.heuristic_confidence:.0f}%, action {report.recommended_action.value}); "
            f"intraday weight decay {decay:.2f}"
        )
        if weight <= 0:
            factor = self._builder.disabled(
                name="Pre-Market Bias",
                score=score,
                detail=detail,
                cluster=FactorCluster.CONTEXT,
            )
        else:
            factor = self._builder.build(
                name="Pre-Market Bias",
                score=score,
                weight=weight,
                detail=detail,
                cluster=FactorCluster.CONTEXT,
            )
        return PremarketFactorBundle(factors=[factor], recommended_action=report.recommended_action)

    async def factors(self) -> List[PredictionFactor]:
        return (await self.bundle()).factors

    async def latest_report(self) -> Optional[PremarketReport]:
        return await self._analyzer.analyze()

    @staticmethod
    def _intraday_decay(now: datetime) -> float:
        local = now.astimezone(IST) if now.tzinfo else IST.localize(now)
        clock = local.time()
        if clock < _OPEN or clock >= _ZERO_AFTER:
            return 0.0 if clock >= _ZERO_AFTER else 1.0
        if clock <= _FULL_UNTIL:
            return 1.0
        elapsed = (clock.hour * 60 + clock.minute) - (_FULL_UNTIL.hour * 60 + _FULL_UNTIL.minute)
        span = (_ZERO_AFTER.hour * 60 + _ZERO_AFTER.minute) - (_FULL_UNTIL.hour * 60 + _FULL_UNTIL.minute)
        return max(0.0, 1.0 - elapsed / span)
