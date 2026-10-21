from sqlalchemy import Column, Date, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base


class PremarketReportRecord(Base):
    __tablename__ = "premarket_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Date, nullable=False, index=True, unique=True)
    overall_sentiment = Column(String(30), nullable=False)
    heuristic_confidence = Column(Float, nullable=False)
    directional_score = Column(Float, nullable=False)
    recommended_action = Column(String(20), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
