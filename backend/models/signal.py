from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Text
from sqlalchemy.sql import func
from database import Base


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    action = Column(String(10), nullable=False)        # BUY | SELL | NEUTRAL
    timeframe = Column(String(5), nullable=False)      # 1d, 15m
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    target_1 = Column(Float, nullable=True)
    target_2 = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False)         # 0–100
    risk_score = Column(String(10), nullable=True)     # LOW | MEDIUM | HIGH
    market_regime = Column(String(30), nullable=True)
    agent_outputs = Column(JSON, nullable=True)        # all 6 agent JSONs
    confidence_breakdown = Column(JSON, nullable=True) # per-agent contributions
    why_not_buy = Column(JSON, nullable=True)          # caution reasons
    ai_explanation = Column(Text, nullable=True)
    is_active = Column(String(1), default="Y")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
