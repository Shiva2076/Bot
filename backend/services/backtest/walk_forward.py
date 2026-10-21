from typing import Dict, List, Sequence

from schemas.trading import Candle
from services.backtest.orb_backtester import OrbIntradayBacktester
from services.backtest.orb_metrics import OrbMetricsReporter


class WalkForwardEvaluator:
    """Chronological train/test split then rolling walk-forward windows."""

    def __init__(self, backtester: OrbIntradayBacktester, metrics: OrbMetricsReporter):
        self._backtester = backtester
        self._metrics = metrics

    def evaluate(
        self,
        symbol: str,
        candles: Sequence[Candle],
        initial_capital: float,
        train_ratio: float = 0.7,
        folds: int = 3,
    ) -> Dict:
        bars = list(candles)
        split = max(50, int(len(bars) * train_ratio))
        train_run = self._backtester.run(symbol, bars[:split], initial_capital)
        test_run = self._backtester.run(symbol, bars[split:], initial_capital)
        baseline = self._buy_hold(bars[split:], initial_capital)

        fold_results = []
        fold_size = max(30, len(bars) // (folds + 1))
        for fold in range(folds):
            test_start = fold_size * (fold + 1)
            test_end = min(len(bars), test_start + fold_size)
            train_slice = bars[:test_start]
            test_slice = bars[test_start:test_end]
            if len(train_slice) < 40 or len(test_slice) < 20:
                continue
            tr = self._backtester.run(symbol, train_slice, initial_capital)
            te = self._backtester.run(symbol, test_slice, initial_capital)
            fold_results.append({
                "fold": fold + 1,
                "train": self._metrics.report(tr["trades"], tr["equity"], initial_capital),
                "test": self._metrics.report(te["trades"], te["equity"], initial_capital),
            })

        return {
            "symbol": symbol,
            "train": self._metrics.report(train_run["trades"], train_run["equity"], initial_capital),
            "test": self._metrics.report(test_run["trades"], test_run["equity"], initial_capital),
            "baseline_buy_hold_test": baseline,
            "walk_forward": fold_results,
            "execution_model": "next_bar_open_after_signal_close",
            "note": "Heuristic research metrics after costs. Not a guarantee of future performance.",
        }

    @staticmethod
    def _buy_hold(bars: List[Candle], capital: float) -> Dict:
        if len(bars) < 2:
            return {"total_return_pct": 0.0, "net_pnl": 0.0}
        ret = (bars[-1].close / bars[0].open - 1.0) * 100
        return {"total_return_pct": round(ret, 2), "net_pnl": round(capital * ret / 100.0, 2)}
