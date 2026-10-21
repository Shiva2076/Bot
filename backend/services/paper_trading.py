"""
Paper Trading Service — manages a virtual portfolio with simulated trades.
(Updated to use in-memory Python dictionaries to run without Docker/Redis)
"""
from datetime import datetime
from typing import Dict, List
import pytz
from config import settings
from schemas.personal_trade import PaperTradeOpened, TradeExitRequest
from services.personal.paper_trade_recorder import paper_trade_recorder

IST = pytz.timezone("Asia/Kolkata")

# In-memory storage instead of Redis
_db = {
    "portfolio": None,
    "positions": [],
    "trades": []
}

class PaperTradingService:
    async def get_portfolio(self) -> Dict:
        if _db["portfolio"]:
            return _db["portfolio"]
        # Initialize portfolio
        portfolio = {
            "cash": settings.starting_capital,
            "total_invested": 0,
            "total_value": settings.starting_capital,
            "starting_capital": settings.starting_capital,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "daily_pnl": 0,
            "created_at": datetime.now(IST).isoformat(),
        }
        _db["portfolio"] = portfolio
        return portfolio

    async def get_positions(self) -> List[Dict]:
        return _db["positions"]

    async def get_trade_history(self) -> List[Dict]:
        return _db["trades"]

    async def open_position(self, symbol: str, signal: Dict, current_price: float) -> Dict:
        """Open a paper trade position."""
        portfolio = await self.get_portfolio()
        positions = await self.get_positions()

        # Check if position already exists
        if any(p["symbol"] == symbol for p in positions):
            return {"error": f"Position already open for {symbol}"}

        # Calculate position size (2% risk per trade)
        cash = portfolio["cash"]
        atr = signal.get("raw", {}).get("ta", {}).get("atr", current_price * 0.015)
        sl_distance = current_price - (signal.get("stop_loss") or current_price * 0.98)
        sl_distance = max(sl_distance, current_price * 0.01)
        risk_amount = cash * 0.02
        quantity = max(1, int(risk_amount / sl_distance))
        invested = quantity * current_price

        if invested > cash:
            quantity = max(1, int(cash * 0.95 / current_price))
            invested = quantity * current_price

        if invested > cash:
            return {"error": "Insufficient funds"}

        position = {
            "id": f"{symbol}_{int(datetime.now().timestamp())}",
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": round(current_price, 2),
            "current_price": round(current_price, 2),
            "invested": round(invested, 2),
            "stop_loss": signal.get("stop_loss"),
            "target_1": signal.get("target_1"),
            "target_2": signal.get("target_2"),
            "unrealized_pnl": 0,
            "unrealized_pnl_pct": 0,
            "confidence": signal.get("confidence"),
            "market_regime": signal.get("market_regime"),
            "entry_time": datetime.now(IST).isoformat(),
            "status": "OPEN",
        }

        position["trade_id"] = await paper_trade_recorder.record_open(PaperTradeOpened(
            symbol=symbol,
            quantity=quantity,
            entry_price=position["entry_price"],
            invested_amount=position["invested"],
            stop_loss=position["stop_loss"],
            target_1=position["target_1"],
            target_2=position["target_2"],
            confidence=position["confidence"],
            market_regime=position["market_regime"],
        ))

        positions.append(position)
        portfolio["cash"] = round(cash - invested, 2)
        portfolio["total_invested"] = round(portfolio["total_invested"] + invested, 2)
        return {"success": True, "position": position}

    async def close_position(self, symbol: str, current_price: float, reason: str = "MANUAL") -> Dict:
        """Close an open paper trade."""
        positions = await self.get_positions()
        portfolio = await self.get_portfolio()
        trade_history = await self.get_trade_history()

        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not pos:
            return {"error": f"No open position for {symbol}"}

        pnl = (current_price - pos["entry_price"]) * pos["quantity"]
        pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"] * 100
        proceeds = current_price * pos["quantity"]

        closed_trade = {
            **pos,
            "exit_price": round(current_price, 2),
            "exit_time": datetime.now(IST).isoformat(),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "exit_reason": reason,
            "status": "CLOSED",
            "outcome": "WIN" if pnl > 0 else ("BREAKEVEN" if pnl == 0 else "LOSS"),
        }

        await paper_trade_recorder.record_close(pos["trade_id"], TradeExitRequest(
            exit_price=current_price,
            exit_time=datetime.now(IST),
            exit_reason=reason,
        ))

        _db["positions"] = [p for p in positions if p["symbol"] != symbol]
        trade_history.append(closed_trade)
        _db["trades"] = trade_history[-200:]

        portfolio["cash"] = round(portfolio["cash"] + proceeds, 2)
        portfolio["total_invested"] = max(0, round(portfolio["total_invested"] - pos["invested"], 2))
        portfolio["total_pnl"] = round(portfolio["total_pnl"] + pnl, 2)
        portfolio["total_pnl_pct"] = round(
            portfolio["total_pnl"] / portfolio["starting_capital"] * 100, 2
        )
        return {"success": True, "trade": closed_trade}

    async def update_positions(self, live_prices: Dict[str, float]):
        """Update unrealized P&L for all open positions."""
        positions = await self.get_positions()
        portfolio = await self.get_portfolio()

        total_market_value = 0
        for pos in positions:
            price = live_prices.get(pos["symbol"])
            if price:
                pos["current_price"] = round(price, 2)
                pos["unrealized_pnl"] = round((price - pos["entry_price"]) * pos["quantity"], 2)
                pos["unrealized_pnl_pct"] = round(
                    (price - pos["entry_price"]) / pos["entry_price"] * 100, 2
                )
            total_market_value += pos.get("current_price", pos["entry_price"]) * pos["quantity"]

        portfolio["total_value"] = round(portfolio["cash"] + total_market_value, 2)
        portfolio["total_pnl"] = round(portfolio["total_value"] - portfolio["starting_capital"], 2)
        portfolio["total_pnl_pct"] = round(
            portfolio["total_pnl"] / portfolio["starting_capital"] * 100, 2
        )

    async def get_stats(self) -> Dict:
        """Get trading statistics."""
        trades = await self.get_trade_history()
        if not trades:
            return {"total_trades": 0}

        wins = [t for t in trades if t.get("outcome") == "WIN"]
        losses = [t for t in trades if t.get("outcome") == "LOSS"]

        return {
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1),
            "avg_win_pct": round(
                sum(t.get("pnl_pct", 0) for t in wins) / max(len(wins), 1), 2
            ),
            "avg_loss_pct": round(
                sum(t.get("pnl_pct", 0) for t in losses) / max(len(losses), 1), 2
            ),
            "best_trade": max(trades, key=lambda t: t.get("pnl", 0), default={}),
            "worst_trade": min(trades, key=lambda t: t.get("pnl", 0), default={}),
        }

paper_trading = PaperTradingService()
