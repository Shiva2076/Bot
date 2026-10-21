"""
Technical Analysis Engine — computes all indicators from raw OHLCV data using pandas.
All indicators implemented natively to avoid external TA library dependency issues.
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(series: pd.Series, fast=12, slow=26, signal=9) -> Dict[str, pd.Series]:
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def compute_bollinger_bands(series: pd.Series, period=20, std=2) -> Dict[str, pd.Series]:
    sma = compute_sma(series, period)
    rolling_std = series.rolling(window=period).std()
    return {
        "upper": sma + std * rolling_std,
        "middle": sma,
        "lower": sma - std * rolling_std,
        "bandwidth": ((sma + std * rolling_std) - (sma - std * rolling_std)) / sma,
    }


def compute_atr(df: pd.DataFrame, period=14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    return vwap


def compute_rvol(df: pd.DataFrame, window: int = 20) -> Optional[float]:
    """
    Relative Volume — compare the most-recent candle's volume to the rolling
    average volume of the same sequential-position candles over the last
    `window` periods.  Returns a ratio; 1.5 = 50% above average.
    """
    if "volume" not in df.columns or len(df) < window + 1:
        return None
    vols = df["volume"].values
    current_vol = float(vols[-1])
    avg_vol = float(np.mean(vols[-window - 1:-1]))
    if avg_vol == 0:
        return None
    return round(current_vol / avg_vol, 2)


def compute_adx(df: pd.DataFrame, period=14) -> Dict[str, pd.Series]:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    atr = compute_atr(df, period)
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(span=period, adjust=False).mean()
    return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}


def compute_supertrend(df: pd.DataFrame, period=10, multiplier=3) -> Dict[str, pd.Series]:
    atr = compute_atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr
    supertrend = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)
    for i in range(1, len(df)):
        if df["close"].iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
        if direction.iloc[i] == 1:
            supertrend.iloc[i] = lower_band.iloc[i]
        else:
            supertrend.iloc[i] = upper_band.iloc[i]
    return {"supertrend": supertrend, "direction": direction}


def compute_support_resistance(df: pd.DataFrame, window=20) -> Dict:
    """Calculate key support and resistance levels using pivot points."""
    recent = df.tail(window)
    highs = recent["high"].nlargest(3).tolist()
    lows = recent["low"].nsmallest(3).tolist()
    last_close = df["close"].iloc[-1]
    last_high = df["high"].iloc[-1]
    last_low = df["low"].iloc[-1]
    pivot = (last_high + last_low + last_close) / 3
    r1 = 2 * pivot - last_low
    s1 = 2 * pivot - last_high
    r2 = pivot + (last_high - last_low)
    s2 = pivot - (last_high - last_low)
    return {
        "pivot": round(pivot, 2),
        "resistance_1": round(r1, 2),
        "resistance_2": round(r2, 2),
        "support_1": round(s1, 2),
        "support_2": round(s2, 2),
        "swing_highs": [round(h, 2) for h in highs],
        "swing_lows": [round(l, 2) for l in lows],
    }


def compute_fibonacci(df: pd.DataFrame, lookback=60) -> Dict:
    """Fibonacci retracement levels from recent swing high/low."""
    recent = df.tail(lookback)
    swing_high = recent["high"].max()
    swing_low = recent["low"].min()
    diff = swing_high - swing_low
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels = {}
    for r in ratios:
        levels[f"fib_{int(r*1000)}"] = round(swing_high - diff * r, 2)
    levels["swing_high"] = round(swing_high, 2)
    levels["swing_low"] = round(swing_low, 2)
    return levels


def run_full_analysis(df: pd.DataFrame) -> Dict:
    """Run all indicators on an OHLCV dataframe. Returns latest values as dict."""
    if df is None or len(df) < 30:
        return {}

    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["close"], inplace=True)

    close = df["close"]
    results: Dict = {}

    # RSI
    rsi = compute_rsi(close)
    results["rsi"] = round(float(rsi.iloc[-1]), 2) if not rsi.empty else None
    results["rsi_prev"] = round(float(rsi.iloc[-2]), 2) if len(rsi) >= 2 else None

    # MACD
    macd = compute_macd(close)
    results["macd_line"] = round(float(macd["macd"].iloc[-1]), 4)
    results["macd_signal"] = round(float(macd["signal"].iloc[-1]), 4)
    results["macd_histogram"] = round(float(macd["histogram"].iloc[-1]), 4)
    results["macd_histogram_prev"] = round(float(macd["histogram"].iloc[-2]), 4) if len(macd["histogram"]) >= 2 else 0
    results["macd_crossover"] = bool(
        macd["macd"].iloc[-1] > macd["signal"].iloc[-1]
        and macd["macd"].iloc[-2] <= macd["signal"].iloc[-2]
    ) if len(macd["macd"]) >= 2 else False
    results["macd_crossunder"] = bool(
        macd["macd"].iloc[-1] < macd["signal"].iloc[-1]
        and macd["macd"].iloc[-2] >= macd["signal"].iloc[-2]
    ) if len(macd["macd"]) >= 2 else False

    # EMAs
    for period in [20, 50, 200]:
        ema = compute_ema(close, period)
        results[f"ema_{period}"] = round(float(ema.iloc[-1]), 2)

    # SMAs
    for period in [50, 200]:
        sma = compute_sma(close, period)
        results[f"sma_{period}"] = round(float(sma.iloc[-1]), 2) if not sma.iloc[-1] != sma.iloc[-1] else None

    # Bollinger Bands
    bb = compute_bollinger_bands(close)
    results["bb_upper"] = round(float(bb["upper"].iloc[-1]), 2)
    results["bb_middle"] = round(float(bb["middle"].iloc[-1]), 2)
    results["bb_lower"] = round(float(bb["lower"].iloc[-1]), 2)
    results["bb_bandwidth"] = round(float(bb["bandwidth"].iloc[-1]), 4)

    # ATR
    if "high" in df.columns and "low" in df.columns:
        atr = compute_atr(df)
        results["atr"] = round(float(atr.iloc[-1]), 2)

        # ADX
        adx_data = compute_adx(df)
        results["adx"] = round(float(adx_data["adx"].iloc[-1]), 2)
        results["plus_di"] = round(float(adx_data["plus_di"].iloc[-1]), 2)
        results["minus_di"] = round(float(adx_data["minus_di"].iloc[-1]), 2)

        # VWAP
        if "volume" in df.columns:
            vwap = compute_vwap(df)
            results["vwap"] = round(float(vwap.iloc[-1]), 2)

        # Supertrend
        st = compute_supertrend(df)
        results["supertrend"] = round(float(st["supertrend"].iloc[-1]), 2)
        results["supertrend_direction"] = int(st["direction"].iloc[-1])

        # Support / Resistance
        results["support_resistance"] = compute_support_resistance(df)

        # Fibonacci
        results["fibonacci"] = compute_fibonacci(df)

    # Volume analysis
    if "volume" in df.columns:
        vol_20 = df["volume"].rolling(20).mean().iloc[-1]
        current_vol = df["volume"].iloc[-1]
        results["volume_ratio"] = round(float(current_vol / vol_20), 2) if vol_20 else 1.0
        results["volume_trend"] = "HIGH" if results["volume_ratio"] > 1.5 else (
            "LOW" if results["volume_ratio"] < 0.7 else "NORMAL"
        )
        # Relative volume (time-slot normalised)
        rvol = compute_rvol(df)
        if rvol is not None:
            results["rvol"] = rvol

    # Price relative to EMAs
    current_price = float(close.iloc[-1])
    results["price"] = round(current_price, 2)
    results["above_ema_20"] = bool(current_price > results.get("ema_20", 0))
    results["above_ema_50"] = bool(current_price > results.get("ema_50", 0))
    results["above_ema_200"] = bool(current_price > results.get("ema_200", 0))

    # 52-week high/low
    year_data = df.tail(252)
    results["week_52_high"] = round(float(year_data["high"].max()), 2) if len(year_data) >= 50 else None
    results["week_52_low"] = round(float(year_data["low"].min()), 2) if len(year_data) >= 50 else None

    return results
