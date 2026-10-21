import asyncio
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from schemas.premarket import MarketSentiment, PremarketReport
from services.premarket.premarket_dependencies import PremarketCollectors, PremarketEngines


class PremarketAnalyzerService:
    def __init__(
        self,
        collectors: PremarketCollectors,
        engines: PremarketEngines,
        cache_seconds: float,
    ):
        self._collectors = collectors
        self._engines = engines
        self._cache_seconds = cache_seconds
        self._cache: Optional[Tuple[float, PremarketReport]] = None

    async def analyze(self, force: bool = False) -> PremarketReport:
        if not force and self._cache and time.time() - self._cache[0] < self._cache_seconds:
            return self._cache[1]
        report = await self._build()
        self._cache = (time.time(), report)
        return report

    async def _build(self) -> PremarketReport:
        now = self._collectors.calendar.now()
        phase = self._collectors.calendar.session_phase(now)
        trading_day = self._collectors.calendar.is_trading_day(now.date())

        global_markets, gift, vix, breadth, nifty, sectors, news_bundle = await asyncio.gather(
            self._collectors.global_markets.collect(),
            self._collectors.gift.collect(),
            self._collectors.vix.collect(),
            self._collectors.breadth.collect(),
            self._collectors.nifty.collect(),
            self._collectors.sectors.collect(),
            self._collectors.news.collect(),
        )
        strongest, weakest = sectors
        news_score, events, news_risks = news_bundle
        strongest_avg = sum(s.change_pct for s in strongest) / len(strongest) if strongest else 0.0
        weakest_avg = sum(s.change_pct for s in weakest) / len(weakest) if weakest else 0.0

        factors, excluded = self._engines.factors.analyze(
            global_markets=global_markets,
            gift=gift,
            breadth=breadth,
            nifty=nifty,
            news_score=news_score,
            strongest_avg=strongest_avg,
            weakest_avg=weakest_avg,
        )
        directional, confidence, sentiment, reasons = self._engines.scorer.score(factors)
        if not trading_day:
            sentiment = MarketSentiment.INSUFFICIENT_DATA
            reasons = ["Market holiday or weekend — no fresh NSE open context."] + reasons

        bullish_count = sum(1 for f in factors if f.included and f.score > 0.15)
        bearish_count = sum(1 for f in factors if f.included and f.score < -0.15)
        conflicting = bullish_count > 0 and bearish_count > 0 and abs(bullish_count - bearish_count) <= 1
        if conflicting:
            confidence = round(max(35.0, confidence - 12.0), 1)

        action = self._engines.scorer.recommend(sentiment, confidence, vix, nifty, conflicting)
        warnings = self._warnings(gift, vix, breadth, nifty, excluded)
        return PremarketReport(
            report_date=now.date(),
            generated_at=datetime.now(timezone.utc),
            session_phase=phase,
            is_trading_day=trading_day,
            overall_sentiment=sentiment,
            heuristic_confidence=confidence,
            directional_score=directional,
            recommended_action=action,
            global_markets=global_markets,
            gift_nifty=gift,
            india_vix=vix,
            breadth=breadth,
            nifty_context=nifty,
            strongest_sectors=strongest,
            weakest_sectors=weakest,
            factors=factors,
            excluded_indicators=excluded,
            bullish_scenarios=self._bullish_scenarios(nifty, strongest),
            bearish_scenarios=self._bearish_scenarios(nifty, weakest),
            key_risks=self._risks(vix, nifty, news_risks, conflicting),
            upcoming_events=events,
            reasons=reasons,
            data_quality_warnings=warnings,
        )

    @staticmethod
    def _warnings(gift, vix, breadth, nifty, excluded: List[str]) -> List[str]:
        warnings: List[str] = []
        for item in (gift, vix, breadth, nifty):
            if getattr(item, "warning", None):
                warnings.append(item.warning)
        if excluded:
            warnings.append("Excluded from score: " + ", ".join(excluded))
        return warnings

    @staticmethod
    def _bullish_scenarios(nifty, strongest) -> List[str]:
        scenarios = []
        if nifty.available and nifty.resistance:
            scenarios.append(f"Hold above prior resistance near {nifty.resistance:.0f} with breadth support.")
        if strongest:
            scenarios.append(f"Leadership continues in {', '.join(s.name for s in strongest[:2])}.")
        scenarios.append("US/Asia risk-on persists into the regular session.")
        return scenarios

    @staticmethod
    def _bearish_scenarios(nifty, weakest) -> List[str]:
        scenarios = []
        if nifty.available and nifty.support:
            scenarios.append(f"Break below prior support near {nifty.support:.0f} with weak breadth.")
        if weakest:
            scenarios.append(f"Pressure deepens in {', '.join(s.name for s in weakest[:2])}.")
        scenarios.append("Overnight global weakness spills into the cash open.")
        return scenarios

    @staticmethod
    def _risks(vix, nifty, news_risks: List[str], conflicting: bool) -> List[str]:
        risks = list(news_risks)
        if vix.available and vix.band.value == "HIGH":
            risks.append(f"India VIX elevated at {vix.value:.1f} — expect wider ranges.")
        if nifty.available and nifty.gap_pct is not None and abs(nifty.gap_pct) >= 0.7:
            risks.append(f"Opening gap {nifty.gap_pct:+.2f}% — gap-fade and trap risk.")
        if conflicting:
            risks.append("Conflicting pre-market factors — confidence reduced.")
        return risks
