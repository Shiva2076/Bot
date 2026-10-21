from datetime import datetime, timezone
from typing import List, Optional, Protocol

from schemas.options import OptionQuote
from schemas.prediction import DataFreshness, FreshnessBasis, GateReason, QuoteFreshness
from schemas.trading import Tick
from services.premarket.trading_calendar import TradingCalendar
from services.trading.exchange_timestamp_validator import ExchangeTimestampValidator

REGULAR_PHASE = "REGULAR"

# Broker/feed clocks may lead local wall clock by a few seconds. Ages within this
# window are treated as just-arrived (age 0, FRESH). Larger lead times stay UNKNOWN
# and never become FRESH.
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 5.0


class TimestampedQuote(Protocol):
    symbol: str
    fetched_at: Optional[datetime]
    exchange_timestamp: Optional[datetime]


class PredictionMarketGateResult:
    __slots__ = ("session_status", "gate_reason", "data_freshness", "quotes")

    def __init__(
        self,
        session_status: str,
        gate_reason: GateReason,
        data_freshness: DataFreshness,
        quotes: List[QuoteFreshness],
    ):
        self.session_status = session_status
        self.gate_reason = gate_reason
        self.data_freshness = data_freshness
        self.quotes = quotes

    @property
    def blocks_action(self) -> bool:
        return self.gate_reason in (
            GateReason.MARKET_CLOSED,
            GateReason.STALE_DATA,
            GateReason.UNKNOWN_FRESHNESS,
        )


class PredictionMarketGate:
    """
    Blocks actionable signals outside REGULAR hours or when required quotes are not
    verified-fresh.

    FRESH requires a genuine exchange timestamp within the age limit relative to the
    evaluation clock passed to evaluate(). Callers must supply a timestamp taken at
    the freshness boundary (after quotes are fetched), not at request start.

    Fetch/cache age alone never promotes a quote to FRESH (recently fetched ≠ verified).
    UNKNOWN blocks actionable predictions.
    """

    def __init__(
        self,
        calendar: TradingCalendar,
        max_exchange_age_seconds: float,
        max_future_skew_seconds: float = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
    ):
        self._calendar = calendar
        self._max_exchange_age_seconds = max_exchange_age_seconds
        self._max_future_skew_seconds = max_future_skew_seconds

    def evaluate(
        self,
        now: datetime,
        ticks: List[Tick],
        option_quotes: Optional[List[OptionQuote]] = None,
    ) -> PredictionMarketGateResult:
        evaluation_now = self._aware(now)
        session_status = self._calendar.session_phase(evaluation_now)
        quotes = [self._from_tick(tick, evaluation_now) for tick in ticks]
        if option_quotes:
            quotes.extend(self._from_option(q, evaluation_now) for q in option_quotes)
        if session_status != REGULAR_PHASE:
            return PredictionMarketGateResult(
                session_status=session_status,
                gate_reason=GateReason.MARKET_CLOSED,
                data_freshness=DataFreshness.MARKET_CLOSED,
                quotes=quotes,
            )
        if any(q.freshness == DataFreshness.STALE for q in quotes):
            return PredictionMarketGateResult(
                session_status=session_status,
                gate_reason=GateReason.STALE_DATA,
                data_freshness=DataFreshness.STALE,
                quotes=quotes,
            )
        if any(q.freshness == DataFreshness.UNKNOWN for q in quotes):
            return PredictionMarketGateResult(
                session_status=session_status,
                gate_reason=GateReason.UNKNOWN_FRESHNESS,
                data_freshness=DataFreshness.UNKNOWN,
                quotes=quotes,
            )
        return PredictionMarketGateResult(
            session_status=session_status,
            gate_reason=GateReason.NONE,
            data_freshness=DataFreshness.FRESH,
            quotes=quotes,
        )

    def _from_tick(self, tick: Tick, now: datetime) -> QuoteFreshness:
        return self._classify(
            symbol=tick.symbol,
            exchange_timestamp=tick.exchange_timestamp,
            fetched_at=tick.fetched_at,
            provider=tick.provider,
            now=now,
        )

    def _from_option(self, quote: OptionQuote, now: datetime) -> QuoteFreshness:
        return self._classify(
            symbol=quote.symbol,
            exchange_timestamp=quote.exchange_timestamp,
            fetched_at=quote.fetched_at,
            provider="ANGEL",
            now=now,
        )

    def _classify(
        self,
        symbol: str,
        exchange_timestamp: Optional[datetime],
        fetched_at: Optional[datetime],
        provider: Optional[str],
        now: datetime,
    ) -> QuoteFreshness:
        fetched = self._aware(fetched_at)
        exchange = self._aware(exchange_timestamp)
        if exchange is not None and not ExchangeTimestampValidator.is_plausible(exchange):
            # Sentinel / garbage exchange clocks are not verified; do not label STALE.
            exchange = None
        if exchange is not None:
            age = (now - exchange).total_seconds()
            if age < -self._max_future_skew_seconds:
                freshness = DataFreshness.UNKNOWN
                basis = FreshnessBasis.UNKNOWN
                verified = False
            elif age < 0:
                # Within documented skew: treat as just-arrived, never inflate freshness window.
                age = 0.0
                freshness = DataFreshness.FRESH
                basis = FreshnessBasis.EXCHANGE
                verified = True
            elif age > self._max_exchange_age_seconds:
                freshness = DataFreshness.STALE
                basis = FreshnessBasis.EXCHANGE
                verified = True
            else:
                freshness = DataFreshness.FRESH
                basis = FreshnessBasis.EXCHANGE
                verified = True
            return QuoteFreshness(
                symbol=symbol,
                exchange_timestamp=exchange,
                fetched_at=fetched,
                quoted_at=exchange,
                age_seconds=round(age, 2),
                provider=provider,
                freshness=freshness,
                basis=basis,
                verified=verified,
            )
        fetch_age = (now - fetched).total_seconds() if fetched is not None else None
        return QuoteFreshness(
            symbol=symbol,
            exchange_timestamp=None,
            fetched_at=fetched,
            quoted_at=fetched,
            age_seconds=None if fetch_age is None else round(fetch_age, 2),
            provider=provider,
            freshness=DataFreshness.UNKNOWN,
            basis=FreshnessBasis.FETCH if fetched is not None else FreshnessBasis.UNKNOWN,
            verified=False,
        )

    @staticmethod
    def _aware(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
