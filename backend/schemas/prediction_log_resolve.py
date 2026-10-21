from pydantic import BaseModel, Field


class PredictionLogResolveResult(BaseModel):
    resolved: int = Field(ge=0)
