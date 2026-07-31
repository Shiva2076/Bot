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
