from sqlalchemy import Column, Date, DateTime, Float, Integer, JSON, String
from sqlalchemy.sql import func

from database import Base


class OptionChainSnapshotRecord(Base):
    __tablename__ = "option_chain_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    underlying = Column(String(20), nullable=False, index=True)
    expiry = Column(Date, nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    spot = Column(Float, nullable=False)
    atm_strike = Column(Float, nullable=False)
    lot_size = Column(Integer, nullable=False)
    strike_window = Column(Float, nullable=False)
    rows = Column(JSON, nullable=False)
    near_call_oi = Column(Float, nullable=False)
    near_put_oi = Column(Float, nullable=False)
    near_spot_pcr = Column(Float, nullable=True)
    atm_iv = Column(Float, nullable=True)
    iv_skew_25d = Column(Float, nullable=True)
    gex_per_1pct = Column(Float, nullable=True)
    data_version = Column(String(40), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FuturesSnapshotRecord(Base):
    __tablename__ = "futures_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    underlying = Column(String(20), nullable=False, index=True)
    contract_symbol = Column(String(80), nullable=False)
    expiry = Column(Date, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ltp = Column(Float, nullable=False)
    spot = Column(Float, nullable=False)
    basis = Column(Float, nullable=False)
    basis_pct = Column(Float, nullable=False)
    open_interest = Column(Float, nullable=False)
    oi_change = Column(Float, nullable=True)
    volume = Column(Float, nullable=False)
    volume_change = Column(Float, nullable=True)
    price_change = Column(Float, nullable=True)
    cvd_proxy = Column(Float, nullable=False)
    data_version = Column(String(40), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
