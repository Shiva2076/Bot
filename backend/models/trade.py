from sqlalchemy import Column, String, Float, Integer, DateTime, JSON
from sqlalchemy.sql import func
from database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    action = Column(String(10), nullable=False)    # BUY | SELL
    trade_type = Column(String(10), default="PAPER")  # PAPER | LIVE

    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=False)
    invested_amount = Column(Float, nullable=False)

    stop_loss = Column(Float, nullable=True)
    target_1 = Column(Float, nullable=True)
    target_2 = Column(Float, nullable=True)

    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    status = Column(String(10), default="OPEN")   # OPEN | CLOSED | SL_HIT | TARGET_HIT

    signal_id = Column(Integer, nullable=True)
    confidence_at_entry = Column(Float, nullable=True)
    market_regime_at_entry = Column(String(30), nullable=True)
    exit_reason = Column(String(50), nullable=True)

    entry_time = Column(DateTime(timezone=True), server_default=func.now())
    exit_time = Column(DateTime(timezone=True), nullable=True)
    holding_days = Column(Integer, nullable=True)
    tags = Column(JSON, nullable=True)
