"""
Backtesting Engine — runs a simple signal-based strategy on historical OHLCV data.
Returns key metrics: Win Rate, CAGR, Sharpe, Max Drawdown, Profit Factor.
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from engines.technical_analysis import (
    compute_rsi, compute_macd, compute_ema, compute_atr
)


def _annualized_return(equity_curve: pd.Series, trading_days: int) -> float:
    if len(equity_curve) < 2 or trading_days == 0:
        return 0.0
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
    years = trading_days / 252
    return (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0


def _sharpe_ratio(daily_returns: pd.Series, risk_free_rate: float = 0.065) -> float:
    """Sharpe ratio annualized. India risk-free ~6.5% (10yr G-sec)."""
    if daily_returns.std() == 0:
        return 0.0
    excess = daily_returns - risk_free_rate / 252
    return float(excess.mean() / excess.std() * np.sqrt(252))


def _max_drawdown(equity_curve: pd.Series) -> float:
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    return float(drawdown.min())


def run_backtest(
    df: pd.DataFrame,
    strategy: str = "rsi_macd",
    initial_capital: float = 1_000_000,
    risk_per_trade_pct: float = 2.0,
    sl_atr_multiplier: float = 2.0,
) -> Dict:
    """
    Run a backtest on historical OHLCV data.
    
    Strategies:
    - rsi_macd: Buy when RSI < 35 and MACD crosses up; Sell when RSI > 65 or MACD crosses down
    - ema_crossover: Buy when EMA20 crosses above EMA50; Sell when EMA20 crosses below EMA50
    - supertrend: Buy/Sell based on Supertrend direction changes
    """
    if df is None or len(df) < 50:
        return {"error": "Not enough data for backtesting (need at least 50 candles)"}

    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["close", "high", "low", "open"], inplace=True)
    df = df.reset_index(drop=True)

    close = df["close"]
    atr = compute_atr(df, 14)

    # --- Generate signals based on strategy ---
    if strategy == "rsi_macd":
        rsi = compute_rsi(close, 14)
        macd = compute_macd(close)
        df["signal"] = 0
        for i in range(1, len(df)):
            macd_cross_up = (
                macd["macd"].iloc[i] > macd["signal"].iloc[i]
                and macd["macd"].iloc[i - 1] <= macd["signal"].iloc[i - 1]
            )
            macd_cross_dn = (
                macd["macd"].iloc[i] < macd["signal"].iloc[i]
                and macd["macd"].iloc[i - 1] >= macd["signal"].iloc[i - 1]
            )
            if rsi.iloc[i] < 35 and macd_cross_up:
                df.loc[i, "signal"] = 1  # BUY
            elif rsi.iloc[i] > 65 and macd_cross_dn:
                df.loc[i, "signal"] = -1  # SELL

    elif strategy == "ema_crossover":
        ema20 = compute_ema(close, 20)
        ema50 = compute_ema(close, 50)
        df["signal"] = 0
        for i in range(1, len(df)):
            if ema20.iloc[i] > ema50.iloc[i] and ema20.iloc[i - 1] <= ema50.iloc[i - 1]:
                df.loc[i, "signal"] = 1
            elif ema20.iloc[i] < ema50.iloc[i] and ema20.iloc[i - 1] >= ema50.iloc[i - 1]:
                df.loc[i, "signal"] = -1

    elif strategy == "ema_trend":
        ema200 = compute_ema(close, 200)
        ema50 = compute_ema(close, 50)
        rsi = compute_rsi(close, 14)
        df["signal"] = 0
        for i in range(200, len(df)):
            if (close.iloc[i] > ema200.iloc[i] and
                    rsi.iloc[i] < 40 and
                    close.iloc[i] > ema50.iloc[i]):
                df.loc[i, "signal"] = 1
            elif close.iloc[i] < ema200.iloc[i] and rsi.iloc[i] > 60:
                df.loc[i, "signal"] = -1
    else:
        return {"error": f"Unknown strategy: {strategy}"}

    # --- Simulate trades ---
    capital = initial_capital
    equity_curve = [capital]
    trades = []
    position = None  # {"entry": price, "qty": int, "sl": float, "target": float, "entry_idx": int}

    for i in range(1, len(df)):
        price = float(close.iloc[i])
        sig = int(df["signal"].iloc[i])

        # Check stop loss / target
        if position:
            if price <= position["sl"]:
                pnl = (position["sl"] - position["entry"]) * position["qty"]
                capital += pnl
                trades.append({
                    "entry": position["entry"],
                    "exit": position["sl"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((position["sl"] - position["entry"]) / position["entry"] * 100, 2),
                    "exit_reason": "SL_HIT",
                    "holding": i - position["entry_idx"],
                })
                position = None
            elif price >= position["target"]:
                pnl = (position["target"] - position["entry"]) * position["qty"]
                capital += pnl
                trades.append({
                    "entry": position["entry"],
                    "exit": position["target"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((position["target"] - position["entry"]) / position["entry"] * 100, 2),
                    "exit_reason": "TARGET_HIT",
                    "holding": i - position["entry_idx"],
                })
                position = None

        # Enter new position
        if sig == 1 and position is None and capital > 0:
            risk_amount = capital * (risk_per_trade_pct / 100)
            sl_distance = float(atr.iloc[i]) * sl_atr_multiplier if not np.isnan(atr.iloc[i]) else price * 0.02
            sl = price - sl_distance
            target = price + sl_distance * 2.5
            qty = max(1, int(risk_amount / sl_distance))
            cost = qty * price
            if cost <= capital:
                capital -= cost
                position = {
                    "entry": price,
                    "qty": qty,
                    "sl": sl,
                    "target": target,
                    "entry_idx": i,
                }
        elif sig == -1 and position:
            pnl = (price - position["entry"]) * position["qty"]
            capital += position["qty"] * price
            trades.append({
                "entry": position["entry"],
                "exit": price,
                "pnl": round(pnl, 2),
                "pnl_pct": round((price - position["entry"]) / position["entry"] * 100, 2),
                "exit_reason": "SIGNAL_EXIT",
                "holding": i - position["entry_idx"],
            })
            position = None

        equity_curve.append(capital + (position["qty"] * price if position else 0))

    equity_series = pd.Series(equity_curve)
    daily_returns = equity_series.pct_change().dropna()
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))

    return {
        "strategy": strategy,
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / max(len(trades), 1) * 100, 2),
        "initial_capital": initial_capital,
        "final_capital": round(equity_series.iloc[-1], 2),
        "net_pnl": round(equity_series.iloc[-1] - initial_capital, 2),
        "total_return_pct": round((equity_series.iloc[-1] / initial_capital - 1) * 100, 2),
        "cagr_pct": round(_annualized_return(equity_series, len(df)) * 100, 2),
        "sharpe_ratio": round(_sharpe_ratio(daily_returns), 2),
        "max_drawdown_pct": round(_max_drawdown(equity_series) * 100, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else float("inf"),
        "avg_holding_days": round(
            sum(t["holding"] for t in trades) / max(len(trades), 1), 1
        ),
        "avg_win_pct": round(
            sum(t["pnl_pct"] for t in wins) / max(len(wins), 1), 2
        ),
        "avg_loss_pct": round(
            sum(t["pnl_pct"] for t in losses) / max(len(losses), 1), 2
        ),
        "equity_curve": [round(v, 2) for v in equity_series.tolist()],
        "trades": trades[-50:],  # last 50 trades for display
    }
