"""
Agent Orchestrator — coordinates all agents and returns the final signal for a symbol.
"""
import asyncio
from typing import Dict, Optional

from services.market_data import market_data_service
from services.news_aggregator import get_news_with_sentiment
from services.institutional_data import get_institutional_data
from services.economic_calendar import get_upcoming_events
from engines.technical_analysis import run_full_analysis
from engines.smart_money import run_smc_analysis
from engines.regime_detector import detect_regime
from agents.historical_agent import find_similar_setups
import agents.technical_agent as tech_agent
import agents.news_agent as news_agent
import agents.historical_agent as hist_agent
import agents.institutional_agent as inst_agent
import agents.risk_agent as risk_agent
import agents.final_decision_agent as final_agent


async def generate_signal(symbol: str, portfolio_heat: float = 0.0) -> Optional[Dict]:
    """
    Run all agents for a symbol and return the final structured signal.
    portfolio_heat: percentage of total capital currently deployed (0–100)
    """
    try:
        # --- Fetch raw data in parallel ---
        ohlcv_task = market_data_service.fetch_ohlcv(symbol, period="2y", interval="1d")
        news_task = get_news_with_sentiment(symbol)
        inst_task = get_institutional_data(symbol)
        nifty_task = market_data_service.fetch_ohlcv("^NSEI", period="1y", interval="1d")
        events = get_upcoming_events()

        ohlcv, news_items, inst_data, nifty_df = await asyncio.gather(
            ohlcv_task, news_task, inst_task, nifty_task,
            return_exceptions=True
        )

        # Handle exceptions gracefully
        ohlcv = ohlcv if isinstance(ohlcv, object) and not isinstance(ohlcv, Exception) else None
        news_items = news_items if isinstance(news_items, list) else []
        inst_data = inst_data if isinstance(inst_data, dict) else {}
        nifty_df = nifty_df if not isinstance(nifty_df, Exception) else None
        events = events if isinstance(events, list) else []

        # --- Run engines ---
        ta = run_full_analysis(ohlcv) if ohlcv is not None else {}
        smc = run_smc_analysis(ohlcv) if ohlcv is not None else {}
        regime = detect_regime(nifty_df) if nifty_df is not None else {"regime": "UNKNOWN", "confidence_modifier": 1.0}

        # Historical pattern matching (CPU-intensive, run in executor)
        loop = asyncio.get_event_loop()
        hist_stats = await loop.run_in_executor(
            None, lambda: find_similar_setups(ohlcv, ta) if ohlcv is not None and ta else {}
        )

        # --- Run all agents ---
        tech_out = tech_agent.analyze(ta, smc, symbol)
        news_out = news_agent.analyze(news_items, symbol)
        hist_out = hist_agent.analyze(hist_stats, symbol)
        inst_out = inst_agent.analyze(inst_data, symbol)
        risk_out = risk_agent.analyze(ta, regime, {}, events, portfolio_heat, symbol)

        # --- Final decision ---
        result = final_agent.synthesize(
            tech_out=tech_out,
            news_out=news_out,
            hist_out=hist_out,
            inst_out=inst_out,
            risk_out=risk_out,
            regime=regime,
            ta=ta,
            symbol=symbol,
        )

        result["raw"] = {
            "ta": ta,
            "smc": smc,
            "regime": regime,
        }

        return result

    except Exception as e:
        import traceback
        print(f"Orchestrator error for {symbol}:")
        traceback.print_exc()
        return None


async def generate_signals_batch(symbols: list, portfolio_heat: float = 0.0) -> Dict:
    """Generate signals for multiple symbols."""
    semaphore = asyncio.Semaphore(10)

    async def _process(symbol):
        async with semaphore:
            return await generate_signal(symbol, portfolio_heat)

    tasks = [_process(s) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    signals = {}
    for i, result in enumerate(results):
        if isinstance(result, dict):
            signals[symbols[i]] = result
    return signals
