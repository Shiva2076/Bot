from sqlalchemy import Column, Date, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base


class PaperSignalRecord(Base):
    __tablename__ = "paper_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_uuid = Column(String(36), nullable=False, unique=True, index=True)
    session_date = Column(Date, nullable=False, index=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, index=True)

    underlying = Column(String(20), nullable=False, index=True)
    strategy = Column(String(40), nullable=False, index=True)
    direction = Column(String(20), nullable=False, index=True)
    score = Column(Float, nullable=False)
    raw_score = Column(Float, nullable=True)
    signal_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    scorer_version = Column(String(40), nullable=False)

    spot_level = Column(Float, nullable=True)
    contract_symbol = Column(String(80), nullable=True, index=True)
    contract_strike = Column(Float, nullable=True)
    contract_expiry = Column(Date, nullable=True)
    contract_option_type = Column(String(5), nullable=True)
    entry_premium = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)

    quote_ltp = Column(Float, nullable=True)
    quote_bid = Column(Float, nullable=True)
    quote_ask = Column(Float, nullable=True)
    quote_volume = Column(Float, nullable=True)
    quote_oi = Column(Float, nullable=True)
    quote_exchange_timestamp = Column(DateTime(timezone=True), nullable=True)
    quote_provider = Column(String(20), nullable=True)
    quote_freshness = Column(String(20), nullable=True)

    gate_reason = Column(String(40), nullable=True, index=True)
    premarket_action = Column(String(20), nullable=True)
    premarket_wait_trigger = Column(String(40), nullable=True)
    freshness_diagnostics = Column(JSON, nullable=True)

    eligibility_status = Column(String(30), nullable=False, index=True)
    execution_status = Column(String(20), nullable=False, default="SKIPPED", index=True)
    rejection_reasons = Column(JSON, nullable=False)

    trade_id = Column(Integer, nullable=True, index=True)
    prediction_snapshot = Column(JSON, nullable=True)
    events = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
