from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from database import Base


class PredictionResearchOutcomeRecord(Base):
    """
    Hypothetical gated-signal research rows. Never read by live trading/prediction paths.
    """

    __tablename__ = "prediction_research_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_log_id = Column(Integer, nullable=False, index=True, unique=True)
    underlying = Column(String(20), nullable=False, index=True)
    predicted_at = Column(DateTime(timezone=True), nullable=False, index=True)
    gate_reason = Column(String(40), nullable=True)
    premarket_wait_trigger = Column(String(40), nullable=True, index=True)
    score = Column(Float, nullable=False)
    implied_direction = Column(String(10), nullable=False)
    spot_result_15m = Column(String(10), nullable=True)
    spot_result_30m = Column(String(10), nullable=True)
    spot_result_60m = Column(String(10), nullable=True)
    spot_change_pct_15m = Column(Float, nullable=True)
    spot_change_pct_30m = Column(Float, nullable=True)
    spot_change_pct_60m = Column(Float, nullable=True)
    hypothetical_net_pnl_15m = Column(Float, nullable=True)
    hypothetical_net_pnl_30m = Column(Float, nullable=True)
    hypothetical_net_pnl_60m = Column(Float, nullable=True)
    hypothetical = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
