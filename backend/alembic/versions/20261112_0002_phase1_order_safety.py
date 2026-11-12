"""Phase 1 order safety, gate logging and paper engine schema.

Revision ID: 20261112_0002
Revises: 20261030_0001
Create Date: 2026-11-12

Ports the idempotent ALTERs that the Bot1 branch ran from database.create_tables()
(migrate_trade_order_audit, migrate_prediction_gate_logging, migrate_paper_engine)
into Alembic, plus the two new tables. Frozen explicit DDL: it does not import models.

Existing trades are tagged LEGACY before order_source becomes NOT NULL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261112_0002"
down_revision: Union[str, Sequence[str], None] = "20261030_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copies of schemas.order_entry values at the time of this revision.
OVERRIDE_REASON_MAX_LENGTH = 500
ORDER_SOURCE_CHECK = "order_source IN ('SYSTEM_SIGNAL', 'MANUAL_OVERRIDE', 'LEGACY')"


def upgrade() -> None:
    # ── trades: order audit ────────────────────────────────────────────────────
    op.add_column("trades", sa.Column("order_source", sa.String(length=20), nullable=True))
    op.add_column("trades", sa.Column("override_reason", sa.String(length=OVERRIDE_REASON_MAX_LENGTH), nullable=True))
    op.add_column("trades", sa.Column("premarket_action_at_entry", sa.String(length=20), nullable=True))
    op.add_column("trades", sa.Column("prediction_gate_at_entry", sa.JSON(), nullable=True))
    op.execute("UPDATE trades SET order_source = 'LEGACY' WHERE order_source IS NULL")
    op.alter_column("trades", "order_source", existing_type=sa.String(length=20), nullable=False)
    op.create_check_constraint("ck_trades_order_source", "trades", ORDER_SOURCE_CHECK)

    # ── trades: paper engine link ──────────────────────────────────────────────
    op.add_column("trades", sa.Column("paper_signal_id", sa.Integer(), nullable=True))
    op.create_index("ix_trades_paper_signal_id", "trades", ["paper_signal_id"], unique=False)
    op.create_index(
        "uq_trades_paper_signal_id",
        "trades",
        ["paper_signal_id"],
        unique=True,
        postgresql_where=sa.text("paper_signal_id IS NOT NULL"),
    )

    # ── prediction_logs: gate / premarket / freshness logging (old rows stay NULL) ──
    op.add_column("prediction_logs", sa.Column("gate_reason", sa.String(length=40), nullable=True))
    op.add_column("prediction_logs", sa.Column("premarket_action", sa.String(length=20), nullable=True))
    op.add_column("prediction_logs", sa.Column("premarket_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prediction_logs", sa.Column("premarket_wait_trigger", sa.String(length=40), nullable=True))
    op.add_column("prediction_logs", sa.Column("freshness_diagnostics", sa.JSON(), nullable=True))
    op.create_index("ix_prediction_logs_gate_reason", "prediction_logs", ["gate_reason"], unique=False)
    op.create_index("ix_prediction_logs_premarket_action", "prediction_logs", ["premarket_action"], unique=False)
    op.create_index(
        "ix_prediction_logs_premarket_wait_trigger", "prediction_logs", ["premarket_wait_trigger"], unique=False
    )

    # ── paper_signals ──────────────────────────────────────────────────────────
    op.create_table(
        "paper_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_uuid", sa.String(length=36), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("underlying", sa.String(length=20), nullable=False),
        sa.Column("strategy", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=True),
        sa.Column("signal_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("scorer_version", sa.String(length=40), nullable=False),
        sa.Column("spot_level", sa.Float(), nullable=True),
        sa.Column("contract_symbol", sa.String(length=80), nullable=True),
        sa.Column("contract_strike", sa.Float(), nullable=True),
        sa.Column("contract_expiry", sa.Date(), nullable=True),
        sa.Column("contract_option_type", sa.String(length=5), nullable=True),
        sa.Column("entry_premium", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("quote_ltp", sa.Float(), nullable=True),
        sa.Column("quote_bid", sa.Float(), nullable=True),
        sa.Column("quote_ask", sa.Float(), nullable=True),
        sa.Column("quote_volume", sa.Float(), nullable=True),
        sa.Column("quote_oi", sa.Float(), nullable=True),
        sa.Column("quote_exchange_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_provider", sa.String(length=20), nullable=True),
        sa.Column("quote_freshness", sa.String(length=20), nullable=True),
        sa.Column("gate_reason", sa.String(length=40), nullable=True),
        sa.Column("premarket_action", sa.String(length=20), nullable=True),
        sa.Column("premarket_wait_trigger", sa.String(length=40), nullable=True),
        sa.Column("freshness_diagnostics", sa.JSON(), nullable=True),
        sa.Column("eligibility_status", sa.String(length=30), nullable=False),
        sa.Column("execution_status", sa.String(length=20), nullable=False),
        sa.Column("rejection_reasons", sa.JSON(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=True),
        sa.Column("prediction_snapshot", sa.JSON(), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_signals_signal_uuid", "paper_signals", ["signal_uuid"], unique=True)
    for column in (
        "session_date", "generated_at", "underlying", "strategy", "direction",
        "contract_symbol", "gate_reason", "eligibility_status", "execution_status", "trade_id",
    ):
        op.create_index(f"ix_paper_signals_{column}", "paper_signals", [column], unique=False)

    # ── prediction_research_outcomes (hypothetical research rows only) ─────────
    op.create_table(
        "prediction_research_outcomes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prediction_log_id", sa.Integer(), nullable=False),
        sa.Column("underlying", sa.String(length=20), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gate_reason", sa.String(length=40), nullable=True),
        sa.Column("premarket_wait_trigger", sa.String(length=40), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("implied_direction", sa.String(length=10), nullable=False),
        sa.Column("spot_result_15m", sa.String(length=10), nullable=True),
        sa.Column("spot_result_30m", sa.String(length=10), nullable=True),
        sa.Column("spot_result_60m", sa.String(length=10), nullable=True),
        sa.Column("spot_change_pct_15m", sa.Float(), nullable=True),
        sa.Column("spot_change_pct_30m", sa.Float(), nullable=True),
        sa.Column("spot_change_pct_60m", sa.Float(), nullable=True),
        sa.Column("hypothetical_net_pnl_15m", sa.Float(), nullable=True),
        sa.Column("hypothetical_net_pnl_30m", sa.Float(), nullable=True),
        sa.Column("hypothetical_net_pnl_60m", sa.Float(), nullable=True),
        sa.Column("hypothetical", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prediction_research_outcomes_prediction_log_id",
        "prediction_research_outcomes", ["prediction_log_id"], unique=True,
    )
    for column in ("underlying", "predicted_at", "premarket_wait_trigger"):
        op.create_index(
            f"ix_prediction_research_outcomes_{column}", "prediction_research_outcomes", [column], unique=False
        )


def downgrade() -> None:
    for column in ("premarket_wait_trigger", "predicted_at", "underlying", "prediction_log_id"):
        op.drop_index(f"ix_prediction_research_outcomes_{column}", table_name="prediction_research_outcomes")
    op.drop_table("prediction_research_outcomes")

    for column in (
        "trade_id", "execution_status", "eligibility_status", "gate_reason", "contract_symbol",
        "direction", "strategy", "underlying", "generated_at", "session_date", "signal_uuid",
    ):
        op.drop_index(f"ix_paper_signals_{column}", table_name="paper_signals")
    op.drop_table("paper_signals")

    op.drop_index("ix_prediction_logs_premarket_wait_trigger", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_premarket_action", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_gate_reason", table_name="prediction_logs")
    for column in ("freshness_diagnostics", "premarket_wait_trigger", "premarket_generated_at",
                   "premarket_action", "gate_reason"):
        op.drop_column("prediction_logs", column)

    op.drop_index("uq_trades_paper_signal_id", table_name="trades")
    op.drop_index("ix_trades_paper_signal_id", table_name="trades")
    op.drop_column("trades", "paper_signal_id")
    op.drop_constraint("ck_trades_order_source", "trades", type_="check")
    for column in ("prediction_gate_at_entry", "premarket_action_at_entry", "override_reason", "order_source"):
        op.drop_column("trades", column)
