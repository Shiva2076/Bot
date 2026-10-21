from datetime import datetime
from typing import List, Optional

from schemas.prediction import ChartStructureFeatures, SessionRange
from schemas.trading import Candle, CandleInterval
from services.prediction.chart_analysis_interpreter import ChartAnalysisInterpreter
from services.prediction.chart_structure_extractor import ChartStructureExtractor
from services.prediction.chart_structure_mapper import ChartStructureMapper
from services.trading.failover_market_data import FailoverMarketData


class ChartStructureShadowCalculator:
    """Shadow-only chart structure: logged for study, never scored."""

    def __init__(
        self,
        market_data: FailoverMarketData,
        mapper: ChartStructureMapper,
        extractor: ChartStructureExtractor,
        interpreter: Optional[ChartAnalysisInterpreter] = None,
    ):
        self._market_data = market_data
        self._mapper = mapper
        self._extractor = extractor
        self._interpreter = interpreter

    async def calculate(
        self,
        symbol: str,
        session_range: Optional[SessionRange],
        atr: float,
        as_of: datetime,
    ) -> ChartStructureFeatures:
        try:
            series_5m = await self._market_data.get_candles(symbol, CandleInterval.FIVE_MINUTES)
            series_15m = await self._market_data.get_candles(symbol, CandleInterval.FIFTEEN_MINUTES)
            series_daily = await self._market_data.get_candles(symbol, CandleInterval.ONE_DAY)
            return self.calculate_from_candles(
                candles_5m=series_5m.candles,
                candles_15m=series_15m.candles,
                daily_candles=series_daily.candles,
                session_range=session_range,
                atr=atr,
                as_of=as_of,
            )
        except Exception as exc:
            return ChartStructureFeatures.unavailable(f"chart structure unavailable: {exc}", as_of)

    def calculate_from_candles(
        self,
        candles_5m: List[Candle],
        candles_15m: List[Candle],
        daily_candles: List[Candle],
        session_range: Optional[SessionRange],
        atr: float,
        as_of: datetime,
    ) -> ChartStructureFeatures:
        try:
            payload = self._mapper.map(
                candles_5m=candles_5m,
                candles_15m=candles_15m,
                daily_candles=daily_candles,
                session_range=session_range,
                atr=atr,
                as_of=as_of,
            )
            features = self._extractor.extract(payload)
            if self._interpreter is not None:
                return self._interpreter.enrich(features)
            return features
        except Exception as exc:
            return ChartStructureFeatures.unavailable(f"chart structure unavailable: {exc}", as_of)
