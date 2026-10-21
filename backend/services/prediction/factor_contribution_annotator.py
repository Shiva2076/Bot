from typing import Dict, List

from schemas.prediction import ClusterScore, FactorCluster, FactorStatus, PredictionFactor


class FactorContributionAnnotator:
    """Attaches signed contribution and percentage share of the raw weighted score."""

    def annotate(self, factors: List[PredictionFactor]) -> List[PredictionFactor]:
        active = [f for f in factors if f.status == FactorStatus.ACTIVE and f.weight > 0]
        total_weight = sum(f.weight for f in active)
        annotated: List[PredictionFactor] = []
        for factor in factors:
            if factor.status == FactorStatus.ACTIVE and factor.weight > 0 and total_weight > 0:
                contribution = factor.score * factor.weight / total_weight
                contribution_pct = contribution * 100.0
                effective_weight = factor.weight
            else:
                contribution = 0.0
                contribution_pct = 0.0
                effective_weight = 0.0
            annotated.append(factor.model_copy(update={
                "contribution": round(contribution, 4),
                "contribution_pct": round(contribution_pct, 2),
                "effective_weight": round(effective_weight, 4),
            }))
        return annotated

    def annotate_clusters(
        self, factors: List[PredictionFactor], clusters: Dict[FactorCluster, ClusterScore]
    ) -> Dict[FactorCluster, ClusterScore]:
        by_cluster: Dict[FactorCluster, float] = {cluster: 0.0 for cluster in FactorCluster}
        for factor in factors:
            by_cluster[factor.cluster] = by_cluster[factor.cluster] + factor.contribution
        return {
            cluster: clusters[cluster].model_copy(update={
                "contribution": round(by_cluster[cluster], 4),
                "contribution_pct": round(by_cluster[cluster] * 100.0, 2),
            })
            for cluster in FactorCluster
        }
