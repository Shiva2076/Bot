from typing import Dict, List

from schemas.prediction import ClusterScore, FactorCluster, FactorStatus, PredictionFactor


class FactorClusterSummarizer:
    def summarize(self, factors: List[PredictionFactor]) -> Dict[FactorCluster, ClusterScore]:
        return {cluster: self._score(cluster, factors) for cluster in FactorCluster}

    @staticmethod
    def _score(cluster: FactorCluster, factors: List[PredictionFactor]) -> ClusterScore:
        members = [f for f in factors if f.cluster == cluster]
        active = [f for f in members if f.status == FactorStatus.ACTIVE and f.weight > 0]
        total_weight = sum(f.weight for f in active)
        return ClusterScore(
            score=round(sum(f.score * f.weight for f in active) / total_weight, 3) if active else None,
            active_factors=len(active),
            total_factors=len(members),
        )
