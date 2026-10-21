from schemas.prediction import FactorBias, FactorCluster, FactorStatus, PredictionFactor
from services.prediction.prediction_weight_budget import PredictionWeightBudget

# Documented intended ACTIVE weight budget at full availability (agent 0.12).
INTENDED_BUDGET = 1.27


def _factor(status: FactorStatus, weight: float, score: float = 0.0) -> PredictionFactor:
    return PredictionFactor(
        name=f"{status.value}-{weight}",
        bias=FactorBias.NEUTRAL,
        score=score,
        weight=weight,
        detail="t",
        cluster=FactorCluster.TREND,
        status=status,
    )


def test_intended_budget_is_documented_sum_not_one():
    budget = PredictionWeightBudget(0.12)
    assert budget.intended_total == INTENDED_BUDGET


def test_coverage_formula_active_weights_over_budget():
    """coverage = min(1, sum(ACTIVE w>0) / 1.27) — weight-budget share, not % of factors."""
    budget = PredictionWeightBudget(0.12)
    factors = [
        _factor(FactorStatus.ACTIVE, 0.12),
        _factor(FactorStatus.ACTIVE, 0.10),
        _factor(FactorStatus.ACTIVE, 0.08),
        _factor(FactorStatus.ACTIVE, 0.07),
        _factor(FactorStatus.ACTIVE, 0.07),
        _factor(FactorStatus.ACTIVE, 0.07),
        _factor(FactorStatus.ACTIVE, 0.05),
        _factor(FactorStatus.ACTIVE, 0.22),
        _factor(FactorStatus.ACTIVE, 0.08),
        _factor(FactorStatus.ACTIVE, 0.05),
        # unavailable / disabled must not count even if score is extreme
        _factor(FactorStatus.UNAVAILABLE, 0.0, score=1.0),
        _factor(FactorStatus.DISABLED, 0.0, score=-1.0),
        _factor(FactorStatus.ACTIVE, 0.0, score=1.0),  # weight 0 excluded
    ]
    active_sum = 0.12 + 0.10 + 0.08 + 0.07 + 0.07 + 0.07 + 0.05 + 0.22 + 0.08 + 0.05
    expected = round(min(1.0, active_sum / INTENDED_BUDGET), 3)
    assert active_sum == 0.91
    assert expected == 0.717
    assert budget.coverage(factors) == expected


def test_coverage_caps_at_one():
    budget = PredictionWeightBudget(0.12)
    factors = [_factor(FactorStatus.ACTIVE, 2.0)]
    assert budget.coverage(factors) == 1.0


def test_coverage_ignores_disabled_and_unavailable_weights():
    budget = PredictionWeightBudget(0.12)
    factors = [
        _factor(FactorStatus.ACTIVE, 0.635),
        _factor(FactorStatus.DISABLED, 0.5),
        _factor(FactorStatus.UNAVAILABLE, 0.3),
    ]
    assert budget.coverage(factors) == 0.5
