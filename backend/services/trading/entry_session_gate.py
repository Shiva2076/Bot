from services.personal.errors import TradeValidationError
from services.premarket.trading_calendar import SPECIAL_SESSION_PHASE, TradingCalendar

PERMITTED_ENTRY_PHASES = frozenset({"REGULAR", SPECIAL_SESSION_PHASE})


class EntrySessionGate:
    """Authoritative session check for new entries; evaluated against the calendar clock at call time."""

    def __init__(self, calendar: TradingCalendar):
        self._calendar = calendar

    def current_phase(self) -> str:
        return self._calendar.session_phase(self._calendar.now())

    def assert_entry_allowed(self) -> str:
        phase = self.current_phase()
        if phase not in PERMITTED_ENTRY_PHASES:
            raise TradeValidationError(
                f"New entries are not permitted in session phase {phase}; "
                "allowed only during the regular session or a configured special session"
            )
        return phase
