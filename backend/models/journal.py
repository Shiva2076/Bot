from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Text
from sqlalchemy.sql import func
from database import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, nullable=True, index=True)
    symbol = Column(String(20), nullable=False)

    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    outcome = Column(String(10), nullable=True)  # WIN | LOSS | BREAKEVEN

    signal_reasons = Column(JSON, nullable=True)
    what_worked = Column(Text, nullable=True)
    what_failed = Column(Text, nullable=True)
    lessons = Column(Text, nullable=True)

    market_regime_at_entry = Column(String(30), nullable=True)
    sector_strength_at_entry = Column(String(20), nullable=True)
    news_sentiment_at_entry = Column(String(10), nullable=True)
    confidence_at_entry = Column(Float, nullable=True)
    ai_explanation = Column(Text, nullable=True)
    holding_days = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
