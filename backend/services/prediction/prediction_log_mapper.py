from typing import Optional

from models.prediction_log import PredictionLogRecord
from schemas.prediction import OptionPrediction
from schemas.prediction_log import DirectionResult, OutcomeStatus, PredictionLogCreate, PredictionLogView


class PredictionLogMapper:
    def __init__(self, scorer_version: str, data_version: str):
        self._scorer_version = scorer_version
        self._data_version = data_version

    def to_create(self, prediction: OptionPrediction) -> PredictionLogCreate:
        contract = prediction.contract
        return PredictionLogCreate(
            underlying=prediction.underlying,
            expiry=prediction.expiry,
            spot=prediction.spot,
            lot_size=prediction.lot_size,
            direction=prediction.direction,
            score=prediction.score,
            confidence=prediction.confidence,
            session_label=prediction.session_label,
            is_expiry_day=prediction.is_expiry_day,
            scorer_version=self._scorer_version,
            data_version=self._data_version,
            factors=[f.model_dump(mode="json") for f in prediction.factors],
            factor_scores={f.name: f.score for f in prediction.factors},
            metrics=prediction.metrics.model_dump(mode="json"),
            cluster_scores={
                cluster.value: score.model_dump(mode="json")
                for cluster, score in prediction.cluster_scores.items()
            },
            regime=prediction.regime.model_dump(mode="json"),
            shadow_features=prediction.shadow.model_dump(mode="json"),
            contract_symbol=None if contract is None else contract.quote.symbol,
            contract_strike=None if contract is None else contract.strike,
            contract_option_type=None if contract is None else contract.option_type,
            entry_premium=None if contract is None else contract.levels.entry,
            predicted_at=prediction.generated_at,
        )

    def to_view(self, row: PredictionLogRecord) -> PredictionLogView:
        return PredictionLogView(
            id=row.id,
            underlying=row.underlying,
            expiry=row.expiry,
            spot=row.spot,
            lot_size=row.lot_size,
            direction=row.direction,
            score=row.score,
            confidence=row.confidence,
            session_label=row.session_label,
            is_expiry_day=row.is_expiry_day,
            scorer_version=row.scorer_version,
            data_version=row.data_version,
            factors=row.factors,
            factor_scores=row.factor_scores,
            metrics=row.metrics,
            cluster_scores=row.cluster_scores,
            regime=row.regime,
            shadow_features=row.shadow_features,
            contract_symbol=row.contract_symbol,
            contract_strike=row.contract_strike,
            contract_option_type=row.contract_option_type,
            entry_premium=row.entry_premium,
            predicted_at=row.predicted_at,
            outcome_status=OutcomeStatus(row.outcome_status),
            spot_15m=row.spot_15m,
            spot_change_pct_15m=row.spot_change_pct_15m,
            direction_result_15m=self._result(row.direction_result_15m),
            premium_15m=row.premium_15m,
            premium_change_pct_15m=row.premium_change_pct_15m,
            net_pnl_15m=row.net_pnl_15m,
            spot_30m=row.spot_30m,
            spot_change_pct_30m=row.spot_change_pct_30m,
            direction_result_30m=self._result(row.direction_result_30m),
            premium_30m=row.premium_30m,
            premium_change_pct_30m=row.premium_change_pct_30m,
            net_pnl_30m=row.net_pnl_30m,
            spot_60m=row.spot_60m,
            spot_change_pct_60m=row.spot_change_pct_60m,
            direction_result_60m=self._result(row.direction_result_60m),
            premium_60m=row.premium_60m,
            premium_change_pct_60m=row.premium_change_pct_60m,
            net_pnl_60m=row.net_pnl_60m,
            outcomes_resolved_at=row.outcomes_resolved_at,
        )

    @staticmethod
    def _result(value: Optional[str]) -> Optional[DirectionResult]:
        if value is None:
            return None
        return DirectionResult(value)
