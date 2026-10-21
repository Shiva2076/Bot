from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base

PRE_FIX_DATA_VERSION = "v0_pre_fix"


class PredictionLogRecord(Base):
    __tablename__ = "prediction_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    underlying = Column(String(20), nullable=False, index=True)
    expiry = Column(Date, nullable=False, index=True)
    spot = Column(Float, nullable=False)
    lot_size = Column(Integer, nullable=True)
    direction = Column(String(20), nullable=False, index=True)
    score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    session_label = Column(String(40), nullable=False)
    is_expiry_day = Column(Boolean, nullable=False, default=False)
    scorer_version = Column(String(40), nullable=False, index=True)
    data_version = Column(String(40), nullable=False, server_default=PRE_FIX_DATA_VERSION, index=True)
    factors = Column(JSON, nullable=False)
    factor_scores = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=False)
    cluster_scores = Column(JSON, nullable=True)
    regime = Column(JSON, nullable=True)
    shadow_features = Column(JSON, nullable=True)
    contract_symbol = Column(String(80), nullable=True)
    contract_strike = Column(Float, nullable=True)
    contract_option_type = Column(String(5), nullable=True)
    entry_premium = Column(Float, nullable=True)
    predicted_at = Column(DateTime(timezone=True), nullable=False, index=True)
    outcome_status = Column(String(20), nullable=False, default="PENDING", index=True)
    spot_15m = Column(Float, nullable=True)
    spot_change_pct_15m = Column(Float, nullable=True)
    direction_result_15m = Column(String(10), nullable=True)
    premium_15m = Column(Float, nullable=True)
    premium_change_pct_15m = Column(Float, nullable=True)
    net_pnl_15m = Column(Float, nullable=True)
    spot_30m = Column(Float, nullable=True)
    spot_change_pct_30m = Column(Float, nullable=True)
    direction_result_30m = Column(String(10), nullable=True)
    premium_30m = Column(Float, nullable=True)
    premium_change_pct_30m = Column(Float, nullable=True)
    net_pnl_30m = Column(Float, nullable=True)
    spot_60m = Column(Float, nullable=True)
    spot_change_pct_60m = Column(Float, nullable=True)
    direction_result_60m = Column(String(10), nullable=True)
    premium_60m = Column(Float, nullable=True)
    premium_change_pct_60m = Column(Float, nullable=True)
    net_pnl_60m = Column(Float, nullable=True)
    outcomes_resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
