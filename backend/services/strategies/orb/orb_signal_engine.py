from datetime import datetime, time, timedelta
from typing import List, Optional, Sequence

import pytz

from schemas.orb import OpeningRange, OrbDecision, OrbSignal
from schemas.personal_trade import TradeAction
from schemas.trading import Candle
from services.risk.position_sizer import PositionSizer
from services.strategies.orb.orb_config import OrbStrategyConfig

IST = pytz.timezone("Asia/Kolkata")


class TimedBar:
    def __init__(self, when: datetime, open_: float, high: float, low: float, close: float, volume: float):
        self.when = when.astimezone(IST) if when.tzinfo else IST.localize(when)
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class OrbSignalEngine:
    """
    Opening Range Breakout on 5m bars.
    Signal is evaluated on bar close; live/paper execution should use the next bar open.
    """

    def __init__(self, config: OrbStrategyConfig, sizer: PositionSizer):
        self._config = config
        self._sizer = sizer

    def evaluate(
        self,
        symbol: str,
        candles: Sequence[Candle],
        capital: float,
        as_of: Optional[datetime] = None,
    ) -> OrbSignal:
        bars = self._to_bars(candles)
        if not bars:
            return OrbSignal(symbol=symbol, session_date=datetime.now(IST).date(), decision=OrbDecision.NO_TRADE,
                             rejection_reason="No candles available", inputs={"bar_count": 0})
        session_day = bars[-1].when.date()
        day_bars = [b for b in bars if b.when.date() == session_day]
        opening = self._opening_range(day_bars)
        if opening is None:
            return OrbSignal(
                symbol=symbol,
                session_date=session_day,
                decision=OrbDecision.NO_TRADE,
                rejection_reason="Opening range incomplete",
                inputs={"day_bars": len(day_bars)},
            )
        cutoff = IST.localize(datetime.combine(session_day, time(
            self._config.invalid_after_hour, self._config.invalid_after_minute
        )))
        post = [b for b in day_bars if b.when >= opening.end and (as_of is None or b.when <= as_of.astimezone(IST))]
        vwap_series = self._vwap(day_bars)
        for idx, bar in enumerate(post):
            if bar.when > cutoff:
                return OrbSignal(
                    symbol=symbol,
                    session_date=session_day,
                    decision=OrbDecision.INVALIDATED,
                    range=opening,
                    rejection_reason=f"No breakout before {cutoff.strftime('%H:%M')} IST",
                    inputs=self._inputs(opening, bar, None, None),
                )
            vol_ma = self._volume_ma(day_bars, bar)
            vwap = vwap_series.get(bar.when)
            long_ok = bar.close > opening.high
            short_ok = bar.close < opening.low
            if long_ok and short_ok:
                continue
            if long_ok:
                reasons = [f"Close {bar.close} broke above range high {opening.high}"]
                if self._config.require_vwap:
                    if vwap is None or bar.close <= vwap:
                        continue
                    reasons.append(f"Close above VWAP {vwap:.2f}")
                if self._config.require_volume:
                    if vol_ma is None or bar.volume < vol_ma * self._config.volume_ma_mult:
                        continue
                    reasons.append(f"Volume {bar.volume:.0f} >= {self._config.volume_ma_mult}x MA {vol_ma:.0f}")
                return self._build_signal(
                    symbol, session_day, TradeAction.BUY, opening, bar, vwap, vol_ma, capital, reasons
                )
            if short_ok:
                reasons = [f"Close {bar.close} broke below range low {opening.low}"]
                if self._config.require_vwap:
                    if vwap is None or bar.close >= vwap:
                        continue
                    reasons.append(f"Close below VWAP {vwap:.2f}")
                if self._config.require_volume:
                    if vol_ma is None or bar.volume < vol_ma * self._config.volume_ma_mult:
                        continue
                    reasons.append(f"Volume {bar.volume:.0f} >= {self._config.volume_ma_mult}x MA {vol_ma:.0f}")
                return self._build_signal(
                    symbol, session_day, TradeAction.SELL, opening, bar, vwap, vol_ma, capital, reasons
                )
        return OrbSignal(
            symbol=symbol,
            session_date=session_day,
            decision=OrbDecision.NO_TRADE,
            range=opening,
            rejection_reason="No confirmed breakout yet",
            inputs={"post_range_bars": len(post)},
        )

    def _build_signal(
        self,
        symbol: str,
        session_day,
        action: TradeAction,
        opening: OpeningRange,
        bar: TimedBar,
        vwap: Optional[float],
        vol_ma: Optional[float],
        capital: float,
        reasons: List[str],
    ) -> OrbSignal:
        entry = bar.close
        stop = opening.low if action == TradeAction.BUY else opening.high
        risk = abs(entry - stop)
        target = entry + self._config.reward_r * risk if action == TradeAction.BUY else entry - self._config.reward_r * risk
        try:
            qty = self._sizer.quantity_from_stop(capital, entry, stop)
        except Exception as e:
            return OrbSignal(
                symbol=symbol,
                session_date=session_day,
                decision=OrbDecision.NO_TRADE,
                range=opening,
                rejection_reason=str(e),
                inputs=self._inputs(opening, bar, vwap, vol_ma),
            )
        return OrbSignal(
            symbol=symbol,
            session_date=session_day,
            decision=OrbDecision.LONG if action == TradeAction.BUY else OrbDecision.SHORT,
            action=action,
            range=opening,
            entry_price=round(entry, 2),
            stop_loss=round(stop, 2),
            target=round(target, 2),
            quantity=qty,
            signal_time=bar.when,
            vwap_at_signal=None if vwap is None else round(vwap, 2),
            volume_at_signal=bar.volume,
            volume_ma_at_signal=None if vol_ma is None else round(vol_ma, 2),
            reasons=reasons,
            inputs=self._inputs(opening, bar, vwap, vol_ma),
        )

    def _opening_range(self, day_bars: List[TimedBar]) -> Optional[OpeningRange]:
        start = day_bars[0].when.replace(
            hour=self._config.session_open_hour,
            minute=self._config.session_open_minute,
            second=0,
            microsecond=0,
        )
        end = start + timedelta(minutes=self._config.range_minutes)
        range_bars = [b for b in day_bars if start <= b.when < end]
        # include bar that starts at 09:15, 09:20, 09:25 for 15m range
        if len(range_bars) < max(1, self._config.range_minutes // 5):
            return None
        return OpeningRange(
            high=max(b.high for b in range_bars),
            low=min(b.low for b in range_bars),
            start=start,
            end=end,
            bar_count=len(range_bars),
        )

    @staticmethod
    def _to_bars(candles: Sequence[Candle]) -> List[TimedBar]:
        bars = []
        for c in candles:
            when = datetime.fromtimestamp(c.time, tz=pytz.utc)
            bars.append(TimedBar(when, c.open, c.high, c.low, c.close, c.volume))
        return sorted(bars, key=lambda b: b.when)

    @staticmethod
    def _vwap(day_bars: List[TimedBar]) -> dict:
        cum_pv = 0.0
        cum_v = 0.0
        out = {}
        for b in day_bars:
            tp = (b.high + b.low + b.close) / 3.0
            cum_pv += tp * b.volume
            cum_v += b.volume
            out[b.when] = cum_pv / cum_v if cum_v else b.close
        return out

    def _volume_ma(self, day_bars: List[TimedBar], bar: TimedBar) -> Optional[float]:
        prior = [b for b in day_bars if b.when <= bar.when]
        window = prior[-self._config.volume_ma_period:]
        if len(window) < self._config.volume_ma_period:
            return None
        return sum(b.volume for b in window) / len(window)

    @staticmethod
    def _inputs(opening: OpeningRange, bar: TimedBar, vwap, vol_ma) -> dict:
        return {
            "range_high": opening.high,
            "range_low": opening.low,
            "bar_time": bar.when.isoformat(),
            "bar_close": bar.close,
            "bar_volume": bar.volume,
            "vwap": vwap,
            "volume_ma": vol_ma,
        }
