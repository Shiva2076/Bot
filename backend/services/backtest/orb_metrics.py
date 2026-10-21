from typing import Dict, List


class OrbMetricsReporter:
    def report(self, trades: List[Dict], equity: List[float], initial_capital: float) -> Dict:
        if not trades:
            return {
                "trade_count": 0,
                "win_rate": 0.0,
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "max_losing_streak": 0,
                "net_pnl": 0.0,
            }
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        net = sum(t["pnl"] for t in trades)
        return {
            "trade_count": len(trades),
            "win_rate": round(len(wins) / len(trades) * 100, 2),
            "expectancy": round(net / len(trades), 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else float("inf"),
            "max_drawdown_pct": round(self._max_dd(equity) * 100, 2),
            "avg_win": round(sum(t["pnl"] for t in wins) / max(len(wins), 1), 2),
            "avg_loss": round(sum(t["pnl"] for t in losses) / max(len(losses), 1), 2),
            "max_losing_streak": self._max_losing_streak(trades),
            "net_pnl": round(net, 2),
            "final_equity": round(equity[-1], 2) if equity else initial_capital,
            "total_return_pct": round((equity[-1] / initial_capital - 1) * 100, 2) if equity else 0.0,
        }

    @staticmethod
    def _max_dd(equity: List[float]) -> float:
        peak = equity[0]
        max_dd = 0.0
        for value in equity:
            peak = max(peak, value)
            max_dd = min(max_dd, (value - peak) / peak if peak else 0.0)
        return abs(max_dd)

    @staticmethod
    def _max_losing_streak(trades: List[Dict]) -> int:
        streak = best = 0
        for trade in trades:
            if trade["pnl"] <= 0:
                streak += 1
                best = max(best, streak)
            else:
                streak = 0
        return best
