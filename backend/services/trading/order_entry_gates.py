from pydantic import BaseModel, ConfigDict

from services.premarket.premarket_analyzer_service import PremarketAnalyzerService
from services.trading.actionable_signal_matcher import ActionableSignalMatcher
from services.trading.entry_session_gate import EntrySessionGate
from services.trading.order_source_classifier import OrderSourceClassifier


class OrderEntryGates(BaseModel):
    """Mandatory gates applied to every new entry; exits never pass through these."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    session: EntrySessionGate
    premarket: PremarketAnalyzerService
    signals: ActionableSignalMatcher
    classifier: OrderSourceClassifier
