from schemas.order_entry import EntryOrigin, OrderClassificationInput, OrderSource
from schemas.premarket import RecommendedAction
from services.personal.errors import TradeValidationError


class OrderSourceClassifier:
    """
    Server-side order source decision. NO_TRADE always rejects a new entry.
    WAIT rejects unless the entry is an explicitly reasoned manual override.
    An order that is not the current actionable signal must carry a reason.
    """

    def classify(self, data: OrderClassificationInput) -> OrderSource:
        if data.premarket_action == RecommendedAction.NO_TRADE:
            raise TradeValidationError("Pre-market NO_TRADE blocks all new entries; no override is possible")
        if data.origin == EntryOrigin.ORB_STRATEGY:
            return self._strategy(data)
        if data.origin == EntryOrigin.AUTO_PAPER:
            return self._auto_paper(data)
        return self._api(data)

    def _strategy(self, data: OrderClassificationInput) -> OrderSource:
        if data.override_reason is not None:
            raise TradeValidationError("Strategy entries cannot carry a manual override reason")
        if data.premarket_action == RecommendedAction.WAIT:
            raise TradeValidationError("Pre-market WAIT blocks strategy entries")
        return OrderSource.SYSTEM_SIGNAL

    def _auto_paper(self, data: OrderClassificationInput) -> OrderSource:
        if data.override_reason is not None:
            raise TradeValidationError("Automatic paper entries cannot carry a manual override reason")
        if data.premarket_action == RecommendedAction.WAIT:
            raise TradeValidationError("Pre-market WAIT blocks automatic paper entries")
        if not data.matches_actionable_signal:
            raise TradeValidationError("Automatic paper entries require a matching actionable system signal")
        return OrderSource.SYSTEM_SIGNAL

    def _api(self, data: OrderClassificationInput) -> OrderSource:
        if data.premarket_action == RecommendedAction.WAIT:
            if data.override_reason is None:
                raise TradeValidationError("Pre-market WAIT blocks new entries; a manual override reason is required")
            return OrderSource.MANUAL_OVERRIDE
        if data.matches_actionable_signal:
            if data.override_reason is not None:
                raise TradeValidationError(
                    "Order matches the current actionable signal; an override reason is inconsistent"
                )
            return OrderSource.SYSTEM_SIGNAL
        if data.override_reason is None:
            raise TradeValidationError(
                "Order does not match the current actionable signal; a manual override reason is required"
            )
        return OrderSource.MANUAL_OVERRIDE
