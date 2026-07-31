from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.sql import func
from database import Base


class Stock(Base):
    __tablename__ = "stocks"

    symbol = Column(String(20), primary_key=True)  # e.g. TCS.NS
    name = Column(String(100), nullable=False)
    sector = Column(String(50), nullable=True)
    index_name = Column(String(20), nullable=True)  # NIFTY50, BANKNIFTY etc.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OHLCVData(Base):
    __tablename__ = "ohlcv_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    timeframe = Column(String(5), nullable=False)  # 1m, 5m, 15m, 1h, 1d
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    delivery_pct = Column(Float, nullable=True)
