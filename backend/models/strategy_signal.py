from sqlalchemy import Column, Date, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base


class StrategySignalRecord(Base):
    __tablename__ = "strategy_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy = Column(String(40), nullable=False, index=True)
    symbol = Column(String(40), nullable=False, index=True)
    session_date = Column(Date, nullable=False, index=True)
    decision = Column(String(20), nullable=False)
    action = Column(String(10), nullable=True)
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=True)
    signal_time = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String(255), nullable=True)
    executed = Column(String(10), nullable=False, default="NO")
    trade_id = Column(Integer, nullable=True)
    outcome = Column(String(20), nullable=True)
    inputs = Column(JSON, nullable=False)
    reasons = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
