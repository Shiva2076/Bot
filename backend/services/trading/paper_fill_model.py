from datetime import datetime, timezone
from typing import List, Optional

from schemas.costs import LegCostBreakdown
from schemas.options import OptionQuote
from schemas.personal_trade import TradeAction
from services.costs.paper_cost_calculator import PaperCostCalculator
from services.trading.exchange_timestamp_validator import ExchangeTimestampValidator
from pydantic import BaseModel

DEFAULT_MAX_SPREAD_PCT = 10.0
DEFAULT_MAX_DATA_AGE_SECONDS = 30.0
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 5.0


class PaperFillResult(BaseModel):
    success: bool
    rejection_reasons: List[str]
    reference_price: Optional[float] = None
    slipped_fill_price: Optional[float] = None
    quantity: int = 0
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_pct: Optional[float] = None
    costs: Optional[LegCostBreakdown] = None
    total_notional: Optional[float] = None
    total_cash_required: Optional[float] = None


class PaperFillModel:
    """
    Validates option market data and simulates realistic BUY fills using the ask price,
    incorporating bid-ask spread checks, liquidity requirements, exchange timestamp
    freshness, and realistic transaction costs and slippage.

    Never fabricates fill prices or uses unverified/stale quotes.
    """

    def __init__(
        self,
        cost_calculator: PaperCostCalculator,
        max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
        max_data_age_seconds: float = DEFAULT_MAX_DATA_AGE_SECONDS,
        max_future_skew_seconds: float = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
    ):
        self._costs = cost_calculator
        self._max_spread_pct = max_spread_pct
        self._max_data_age_seconds = max_data_age_seconds
        self._max_future_skew_seconds = max_future_skew_seconds

    @property
    def max_spread_pct(self) -> float:
        return self._max_spread_pct

    @property
    def max_data_age_seconds(self) -> float:
        return self._max_data_age_seconds

    def evaluate_buy_fill(
        self,
        quote: Optional[OptionQuote],
        quantity: int,
        evaluation_time: datetime,
    ) -> PaperFillResult:
        reasons: List[str] = []

        if quantity <= 0:
            reasons.append("Intended quantity must be positive")

        if quote is None:
            reasons.append("Option quote is missing")
            return PaperFillResult(
                success=False,
                rejection_reasons=reasons,
                quantity=quantity,
            )

        bid = quote.bid
        ask = quote.ask
        spread_pct: Optional[float] = None

        if ask is None or ask <= 0:
            reasons.append(f"Missing or non-positive ask price (ask: {ask})")
        if bid is None or bid <= 0:
            reasons.append(f"Missing or non-positive bid price (bid: {bid})")

        if ask is not None and bid is not None and ask > 0 and bid > 0:
            if bid > ask:
                reasons.append(f"Crossed market quotes: bid ({bid}) exceeds ask ({ask})")
            else:
                spread_pct = round(((ask - bid) / ask) * 100.0, 4)
                if spread_pct > self._max_spread_pct:
                    reasons.append(
                        f"Bid-ask spread too wide ({spread_pct:.2f}% > limit {self._max_spread_pct:.2f}%)"
                    )

        if quote.volume is None or quote.volume <= 0:
            reasons.append(
                f"Zero or missing trade volume ({quote.volume}) indicates illiquid contract"
            )

        ex_ts = quote.exchange_timestamp
        if ex_ts is None:
            reasons.append(
                "Missing verified exchange timestamp from quote feed (fetch time not permitted)"
            )
        elif not ExchangeTimestampValidator.is_plausible(ex_ts):
            reasons.append(f"Exchange timestamp implausible or corrupted ({ex_ts})")
        else:
            if ex_ts.tzinfo is None:
                ex_ts = ex_ts.replace(tzinfo=timezone.utc)
            now_utc = (
                evaluation_time.astimezone(timezone.utc)
                if evaluation_time.tzinfo is not None
                else evaluation_time.replace(tzinfo=timezone.utc)
            )
            ex_utc = ex_ts.astimezone(timezone.utc)
            age = (now_utc - ex_utc).total_seconds()
            if age < -self._max_future_skew_seconds:
                reasons.append(
                    f"Exchange timestamp is in the future beyond tolerance (age: {age:.1f}s < -{self._max_future_skew_seconds:.1f}s)"
                )
            elif age > self._max_data_age_seconds:
                reasons.append(
                    f"Exchange quote data is stale ({age:.1f}s > limit {self._max_data_age_seconds:.1f}s)"
                )

        if reasons:
            return PaperFillResult(
                success=False,
                rejection_reasons=reasons,
                reference_price=ask,
                quantity=quantity,
                bid=bid,
                ask=ask,
                spread_pct=spread_pct,
            )

        # All checks passed: apply slippage and transaction costs exactly once via PaperCostCalculator
        # For an option BUY order, the reference execution price is the top-of-book ask.
        assert ask is not None
        leg = self._costs.leg_cost(ask, quantity, TradeAction.BUY, is_entry=True)
        slipped_price = leg.slipped_price
        total_notional = leg.notional
        total_cash_required = round(total_notional + leg.total_fees, 2)

        return PaperFillResult(
            success=True,
            rejection_reasons=[],
            reference_price=ask,
            slipped_fill_price=slipped_price,
            quantity=quantity,
            bid=bid,
            ask=ask,
            spread_pct=spread_pct,
            costs=leg,
            total_notional=total_notional,
            total_cash_required=total_cash_required,
        )
