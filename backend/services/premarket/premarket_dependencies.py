from pydantic import BaseModel, ConfigDict

from services.premarket.breadth_collector import BreadthCollector
from services.premarket.gift_nifty_provider import GiftNiftyProvider
from services.premarket.global_markets_collector import GlobalMarketsCollector
from services.premarket.india_vix_provider import IndiaVixProvider
from services.premarket.news_risk_collector import NewsRiskCollector
from services.premarket.nifty_context_collector import NiftyContextCollector
from services.premarket.premarket_factor_analyzer import PremarketFactorAnalyzer
from services.premarket.premarket_scorer import PremarketScorer
from services.premarket.sector_collector import SectorCollector
from services.premarket.trading_calendar import TradingCalendar


class PremarketCollectors(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    calendar: TradingCalendar
    global_markets: GlobalMarketsCollector
    gift: GiftNiftyProvider
    vix: IndiaVixProvider
    breadth: BreadthCollector
    nifty: NiftyContextCollector
    sectors: SectorCollector
    news: NewsRiskCollector


class PremarketEngines(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    factors: PremarketFactorAnalyzer
    scorer: PremarketScorer
