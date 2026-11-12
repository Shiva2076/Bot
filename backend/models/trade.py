from sqlalchemy import CheckConstraint, Column, DateTime, Float, Index, Integer, JSON, String
from sqlalchemy.sql import func
from database import Base
from schemas.order_entry import OVERRIDE_REASON_MAX_LENGTH, OrderSource

ORDER_SOURCE_CHECK = "order_source IN ({})".format(", ".join(f"'{s.value}'" for s in OrderSource))


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(ORDER_SOURCE_CHECK, name="ck_trades_order_source"),
        Index(
            "uq_trades_paper_signal_id",
            "paper_signal_id",
            unique=True,
            postgresql_where=(Column("paper_signal_id").isnot(None)),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(40), nullable=False, index=True)
    action = Column(String(10), nullable=False)    # BUY | SELL
    trade_type = Column(String(10), default="PAPER")  # PAPER | MANUAL

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
    paper_signal_id = Column(Integer, nullable=True, index=True)
    confidence_at_entry = Column(Float, nullable=True)
    market_regime_at_entry = Column(String(30), nullable=True)
    exit_reason = Column(String(50), nullable=True)

    order_source = Column(String(20), nullable=False)
    override_reason = Column(String(OVERRIDE_REASON_MAX_LENGTH), nullable=True)
    premarket_action_at_entry = Column(String(20), nullable=True)
    prediction_gate_at_entry = Column(JSON, nullable=True)

    entry_time = Column(DateTime(timezone=True), server_default=func.now())
    exit_time = Column(DateTime(timezone=True), nullable=True)
    holding_days = Column(Integer, nullable=True)
    tags = Column(JSON, nullable=True)
