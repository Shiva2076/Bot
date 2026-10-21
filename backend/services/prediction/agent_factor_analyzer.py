from typing import Dict

from schemas.prediction import AgentConsensus, FactorCluster, PredictionFactor
from services.prediction.factor_builder import PredictionFactorBuilder

# Overlap note (documented, not removed in Section A):
# AgentConsensus is built by agents/orchestrator.generate_signal, which still runs
# technical_agent + historical_agent on the same RSI/MACD/EMA/Supertrend/ADX stack
# already scored as TREND/LEVELS factors. News, institutional and risk agents are
# the non-overlapping residual. Weight is kept low until logs justify more.
ACTION_SCORES: Dict[str, float] = {"BUY": 1.0, "SELL": -1.0, "NEUTRAL": 0.0}


class AgentFactorAnalyzer:
    def __init__(self, builder: PredictionFactorBuilder, weight: float):
        if not 0.10 <= weight <= 0.15:
            raise ValueError("AI Agents weight must be in [0.10, 0.15] until logs justify more")
        self._builder = builder
        self._weight = weight

    def analyze(self, consensus: AgentConsensus) -> PredictionFactor:
        direction = ACTION_SCORES[consensus.action]
        bounded = max(0.0, min(1.0, consensus.confidence / 100.0))
        score = direction * bounded
        return self._builder.build(
            name="AI Agents",
            score=score,
            weight=self._weight,
            detail=(
                f"Agents say {consensus.action} at {consensus.confidence:.0f}% heuristic "
                f"({consensus.bullish_agents} bullish, {consensus.bearish_agents} bearish); "
                f"score=direction×confidence/100={score:+.2f}. "
                f"Technical/historical agents overlap scored indicators — residual is news/risk/FII"
            ),
            cluster=FactorCluster.AGENTS,
        )
