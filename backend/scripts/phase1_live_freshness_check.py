"""
Phase 1 open item 3: live-session exchange-timestamp check for the NIFTY index, the
near-month NIFTY future and option strikes around ATM.

For each instrument it prints the raw Angel exchTradeTime / exchFeedTime, what was parsed,
and the verdict the order-path risk gate would give (PASS / STALE / FUTURE / MISSING),
plus what the verdict would be if freshness were judged on feed time alone (for comparison
only; the gate judges on trade time, see AngelQuoteMapper.parse_exchange_timestamp).

Read-only: never places orders, never prints credentials or tokens.
Run during market hours (09:15-15:30 IST), from backend/:
    .venv\\Scripts\\python -m scripts.phase1_live_freshness_check [strikes_each_side]
If fresh quotes are rejected in market hours, treat it as a parsing finding; do not loosen
the rule.
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from schemas.options import OptionUnderlying  # noqa: E402
from services.brokers.angel.quote_mapper import AngelQuoteMapper  # noqa: E402
from services.trading.providers import angel_master, angel_provider, trading_calendar  # noqa: E402

INDEX_SYMBOL = "^NSEI"


def verdict(ts: Optional[datetime], now: datetime) -> Tuple[str, Optional[float]]:
    if ts is None:
        return "MISSING", None
    age = (now - ts).total_seconds()
    if age < -settings.risk_max_future_skew_seconds:
        return "FUTURE", age
    if age > settings.risk_max_data_age_seconds:
        return "STALE", age
    return "PASS", age


async def pick_symbols(strikes_each_side: int) -> List[Tuple[str, str]]:
    picked: List[Tuple[str, str]] = [(INDEX_SYMBOL, "index")]
    future = await angel_master.near_future(OptionUnderlying.NIFTY)
    if future is not None:
        picked.append((future.symbol, f"future {future.expiry}"))
    spot_tick = await angel_provider.get_tick(INDEX_SYMBOL)
    expiries = await angel_master.expiries(OptionUnderlying.NIFTY)
    if spot_tick is None or not expiries:
        return picked
    chain = await angel_master.chain_contracts(OptionUnderlying.NIFTY, expiries[0])
    strikes = sorted({c.strike for c in chain})
    if not strikes:
        return picked
    atm = min(strikes, key=lambda s: abs(s - spot_tick.ltp))
    i = strikes.index(atm)
    window = set(strikes[max(0, i - strikes_each_side): i + strikes_each_side + 1])
    for c in sorted(chain, key=lambda c: (c.strike, c.option_type.value)):
        if c.strike in window:
            tag = "ATM" if c.strike == atm else f"{c.strike - atm:+.0f}"
            picked.append((c.symbol, f"option {c.option_type.value} {tag} exp {c.expiry}"))
    return picked


async def main(strikes_each_side: int) -> None:
    now_ist = trading_calendar.now()
    phase = trading_calendar.session_phase(now_ist)
    print(f"run at {now_ist:%Y-%m-%d %H:%M:%S} IST, session phase {phase}; "
          f"risk_max_data_age_seconds={settings.risk_max_data_age_seconds:.0f}, "
          f"risk_max_future_skew_seconds={settings.risk_max_future_skew_seconds:.0f}")
    if phase != "REGULAR":
        print("NOTE: not in the regular session; results only prove parsing, not live freshness.")

    picked = await pick_symbols(strikes_each_side)
    quotes = await angel_provider.get_quotes([s for s, _ in picked])
    now = datetime.now(timezone.utc)

    counts = {"PASS": 0, "STALE": 0, "FUTURE": 0, "MISSING": 0, "NO_QUOTE": 0}
    feed_pass = 0
    print(f"\n{'symbol':<24} {'kind':<30} {'exchTradeTime(raw)':<22} {'exchFeedTime(raw)':<22} "
          f"{'gate':<8} {'age_s':>8} {'feed-only':<9}")
    for symbol, kind in picked:
        quote = quotes.get(symbol)
        if quote is None:
            counts["NO_QUOTE"] += 1
            print(f"{symbol:<24} {kind:<30} {'-':<22} {'-':<22} {'NO_QUOTE':<8}")
            continue
        chosen = AngelQuoteMapper.parse_exchange_timestamp(quote)
        gate, age = verdict(chosen, now)
        feed_gate, _ = verdict(AngelQuoteMapper.parse_angel_time(quote.exch_feed_time), now)
        counts[gate] += 1
        feed_pass += feed_gate == "PASS"
        print(f"{symbol:<24} {kind:<30} {str(quote.exch_trade_time):<22} {str(quote.exch_feed_time):<22} "
              f"{gate:<8} {'' if age is None else f'{age:8.1f}'} {feed_gate:<9}")

    total = len(picked)
    print(f"\nsummary: {total} instruments | gate PASS {counts['PASS']} | STALE {counts['STALE']} | "
          f"FUTURE {counts['FUTURE']} | MISSING {counts['MISSING']} | NO_QUOTE {counts['NO_QUOTE']}")
    print(f"pass rate on the order gate: {counts['PASS'] / total:.0%}  "
          f"(feed-time-only, for comparison: {feed_pass / total:.0%})")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2))
