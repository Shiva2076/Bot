"""
Dry-run PreTradeRiskGate on live ticks for NIFTY future + three option strikes.
No orders, no DB writes.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import get_settings
from schemas.options import OptionUnderlying
from schemas.personal_trade import TradeAction
from schemas.premarket import RecommendedAction
from schemas.risk import PreTradeOrderContext
from services.risk.pre_trade_risk_gate import PreTradeRiskGate
from services.trading.providers import angel_master, market_data, option_chain_service, paper_cost_calculator


async def main() -> None:
    settings = get_settings()
    gate = PreTradeRiskGate(
        max_data_age_seconds=settings.risk_max_data_age_seconds,
        max_risk_per_trade_pct=settings.risk_per_trade_pct,
        daily_loss_limit_pct=settings.risk_daily_loss_limit_pct,
        max_open_positions=settings.risk_max_open_positions,
        cost_calculator=paper_cost_calculator,
    )
    expiries = await option_chain_service.get_expiries(OptionUnderlying.NIFTY)
    expiry = expiries.expiries[0]
    chain = await option_chain_service.get_chain(OptionUnderlying.NIFTY, expiry)
    future = await angel_master.near_future(OptionUnderlying.NIFTY)
    option_symbols = []
    for row in chain.rows:
        if abs(row.strike - chain.atm_strike) > 100:
            continue
        if row.call is not None:
            option_symbols.append(row.call.symbol)
        if row.put is not None:
            option_symbols.append(row.put.symbol)
        if len(option_symbols) >= 3:
            break
    symbols = ([future.symbol] if future is not None else []) + option_symbols[:3]
    ticks = await market_data.get_ticks(symbols)
    print(f"dry_run_at={datetime.now(timezone.utc).isoformat()} symbols={symbols}")
    for symbol in symbols:
        tick = ticks.get(symbol)
        if tick is None:
            print(f"{symbol}: NO TICK")
            continue
        exchange_ts = tick.exchange_timestamp
        age = None
        if exchange_ts is not None:
            ts = exchange_ts if exchange_ts.tzinfo else exchange_ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
        decision = gate.evaluate(
            PreTradeOrderContext(
                symbol=symbol,
                action=TradeAction.BUY,
                quantity=settings.nifty_lot_size,
                entry_price=tick.ltp if tick.ltp > 0 else 1.0,
                stop_loss=None,
                tick_timestamp=tick.timestamp
                if isinstance(tick.timestamp, datetime)
                else datetime.now(timezone.utc),
                tick_provider=tick.provider or "UNKNOWN",
                exchange_timestamp=exchange_ts,
                open_positions=0,
                starting_capital=settings.starting_capital,
                available_cash=settings.starting_capital,
                realized_pnl_today=0.0,
                kill_switch_active=False,
                premarket_action=RecommendedAction.WATCH,
                data_warnings=[],
            )
        )
        print(
            f"{symbol}: ltp={tick.ltp} exchange_ts={exchange_ts} age_s={None if age is None else round(age, 2)} "
            f"allowed={decision.allowed} reasons={decision.reasons}"
        )


if __name__ == "__main__":
    asyncio.run(main())
