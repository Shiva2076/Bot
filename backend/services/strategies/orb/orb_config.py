from pydantic import BaseModel, Field


class OrbStrategyConfig(BaseModel):
    range_minutes: int = Field(default=15, gt=0)
    reward_r: float = Field(default=2.0, gt=0)
    invalid_after_hour: int = Field(default=11, ge=0, le=23)
    invalid_after_minute: int = Field(default=0, ge=0, le=59)
    require_vwap: bool = True
    require_volume: bool = True
    volume_ma_period: int = Field(default=20, gt=1)
    volume_ma_mult: float = Field(default=1.2, gt=0)
    session_open_hour: int = 9
    session_open_minute: int = 15
