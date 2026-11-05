from schemas.order_entry import PredictionGateSnapshot, SignalMatch
from schemas.personal_trade import TradeAction
from schemas.prediction import GateReason, OptionPrediction, PredictionDirection
from schemas.trading import Instrument, InstrumentKind, MarketOrderRequest
from services.options.option_contract_resolver import OptionContractResolver
from services.prediction.option_prediction_service import OptionPredictionService

ACTIONABLE_DIRECTIONS = frozenset({PredictionDirection.CALL, PredictionDirection.PUT})


class PredictionGateSnapshotMapper:
    def from_prediction(self, prediction: OptionPrediction) -> PredictionGateSnapshot:
        return PredictionGateSnapshot(
            available=True,
            direction=prediction.direction,
            gate_reason=prediction.gate_reason,
            data_freshness=prediction.data_freshness,
            session_status=prediction.session_status,
            contract_symbol=prediction.contract.quote.symbol if prediction.contract else None,
            generated_at=prediction.generated_at,
            log_id=prediction.log_id,
        )

    def unavailable(self, note: str) -> PredictionGateSnapshot:
        return PredictionGateSnapshot(available=False, note=note)


class ActionableSignalMatcher:
    """Matches an entry against the server's current actionable option prediction."""

    def __init__(
        self,
        predictions: OptionPredictionService,
        contracts: OptionContractResolver,
        snapshots: PredictionGateSnapshotMapper,
    ):
        self._predictions = predictions
        self._contracts = contracts
        self._snapshots = snapshots

    async def match(self, instrument: Instrument, request: MarketOrderRequest) -> SignalMatch:
        if instrument.kind != InstrumentKind.OPTION:
            return SignalMatch(matched=False, snapshot=self._snapshots.unavailable("No prediction for non-option instruments"))
        parsed = await self._contracts.resolve(instrument.symbol)
        if parsed is None:
            return SignalMatch(matched=False, snapshot=self._snapshots.unavailable("Unparseable option symbol"))
        try:
            prediction = await self._predictions.predict(parsed.underlying, parsed.expiry)
        except Exception as exc:
            return SignalMatch(
                matched=False,
                snapshot=self._snapshots.unavailable(f"Prediction unavailable: {type(exc).__name__}"),
            )
        matched = (
            prediction.contract is not None
            and prediction.gate_reason == GateReason.NONE
            and prediction.direction in ACTIONABLE_DIRECTIONS
            and prediction.contract.quote.symbol == instrument.symbol
            and request.action == TradeAction.BUY
        )
        return SignalMatch(matched=matched, snapshot=self._snapshots.from_prediction(prediction))
