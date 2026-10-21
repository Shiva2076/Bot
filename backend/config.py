from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

    # Redis (Not used locally anymore, kept for compat)
    redis_url: str = "redis://localhost:6379/0"

    # AI
    gemini_api_key: str = ""

    # Paper Trading
    starting_capital: float = 1_000_000.0  # ₹10 Lakhs
    app_api_key: str = ""

    # Risk gate (paper)
    risk_max_data_age_seconds: float = 30.0
    risk_per_trade_pct: float = 1.0
    risk_daily_loss_limit_pct: float = 3.0
    risk_max_open_positions: int = 5
    risk_enforce_premarket_gate: bool = True

    # Paper cost model (single calculator; do not stack elsewhere)
    cost_brokerage_pct: float = 0.03
    cost_brokerage_flat: float = 20.0
    cost_exchange_txn_pct: float = 0.00345
    cost_sebi_pct: float = 0.0001
    cost_stamp_duty_buy_pct: float = 0.015
    cost_stt_sell_pct: float = 0.025
    cost_gst_pct: float = 18.0
    cost_slippage_bps: float = 5.0

    # ORB strategy
    orb_range_minutes: int = 15
    orb_candle_interval: str = "5m"
    orb_reward_r: float = 2.0
    orb_invalid_after_hour: int = 11
    orb_invalid_after_minute: int = 0
    orb_require_vwap: bool = True
    orb_require_volume: bool = True
    orb_volume_ma_period: int = 20
    orb_volume_ma_mult: float = 1.2

    # Trading screen
    nifty_lot_size: int = 65
    banknifty_lot_size: int = 30
    sensex_lot_size: int = 20
    tick_cache_seconds: float = 3.0
    risk_monitor_interval_seconds: float = 5.0
    prediction_cache_seconds: float = 60.0
    prediction_scorer_version: str = "v1.3_freshness"
    prediction_data_version: str = "v1_data_fixes"
    prediction_outcome_flat_band_pct: float = 0.05
    prediction_outcome_monitor_seconds: float = 60.0
    prediction_initial_balance_minutes: int = 60
    prediction_opening_range_minutes: int = 15
    prediction_regime_trend_adx: float = 25.0
    prediction_regime_range_adx: float = 20.0
    prediction_strike_window_nifty: float = 500.0
    prediction_strike_window_banknifty: float = 1500.0
    prediction_agent_weight: float = 0.12
    prediction_max_quote_age_seconds: float = 30.0
    prediction_min_coverage: float = 0.50
    prediction_cluster_disagreement_epsilon: float = 0.15
    prediction_min_signal_score: float = 50.0
    prediction_oi_wall_proximity_points: float = 500.0
    prediction_max_pain_zero_dte: int = 3
    prediction_adx_range_multiplier: float = 0.70
    prediction_adx_trend_multiplier: float = 1.0
    options_risk_free_rate: float = 0.065
    snapshot_interval_seconds: float = 180.0
    snapshot_underlyings: str = "NIFTY"
    agent_consensus_cache_seconds: float = 300.0

    # Pre-market analyzer (strategy settings, not universal truths)
    premarket_cache_seconds: float = 120.0
    premarket_scheduler_hour: int = 8
    premarket_scheduler_minute: int = 45
    premarket_nse_holidays: str = "2026-01-26,2026-03-03,2026-03-26,2026-03-31,2026-04-03,2026-04-14,2026-05-01,2026-08-15,2026-10-02,2026-11-09,2026-12-25"
    premarket_sentiment_bullish_pct: float = 0.25
    premarket_sentiment_bearish_pct: float = -0.25
    premarket_vix_low: float = 12.0
    premarket_vix_high: float = 18.0
    premarket_large_gap_pct: float = 0.8
    premarket_weight_global: float = 0.20
    premarket_weight_gift: float = 0.25
    premarket_weight_breadth: float = 0.25
    premarket_weight_nifty: float = 0.20
    premarket_weight_news: float = 0.05
    premarket_weight_sector: float = 0.05
    premarket_score_bullish: float = 0.18
    premarket_score_bearish: float = -0.18
    premarket_min_factors: int = 2

    # Angel One SmartAPI
    angel_api_key: str = ""
    angel_client_code: str = ""
    angel_pin: str = ""
    angel_totp_secret: str = ""
    angel_quote_cache_seconds: float = 3.0
    angel_requests_per_second: int = 4
    angel_max_concurrent_requests: int = 2

    # App
    app_env: str = "development"
    debug: bool = True
    cors_origins: str = "http://localhost:5173"

    # Telegram (optional)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
