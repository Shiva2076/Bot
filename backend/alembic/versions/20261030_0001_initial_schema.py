"""Frozen initial schema for all application tables.

Revision ID: 20261030_0001
Revises:
Create Date: 2026-10-30

This revision is frozen explicit DDL. It does not call Base.metadata.create_all().
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261030_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sector", sa.String(length=50), nullable=True),
        sa.Column("index_name", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("symbol"),
    )

    op.create_table(
        "ohlcv_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeframe", sa.String(length=5), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("delivery_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ohlcv_data_symbol", "ohlcv_data", ["symbol"], unique=False)
    op.create_index("ix_ohlcv_data_timestamp", "ohlcv_data", ["timestamp"], unique=False)

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("timeframe", sa.String(length=5), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("target_1", sa.Float(), nullable=True),
        sa.Column("target_2", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.String(length=10), nullable=True),
        sa.Column("market_regime", sa.String(length=30), nullable=True),
        sa.Column("agent_outputs", sa.JSON(), nullable=True),
        sa.Column("confidence_breakdown", sa.JSON(), nullable=True),
        sa.Column("why_not_buy", sa.JSON(), nullable=True),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.String(length=1), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_symbol", "signals", ["symbol"], unique=False)

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("trade_type", sa.String(length=10), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("invested_amount", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("target_1", sa.Float(), nullable=True),
        sa.Column("target_2", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=True),
        sa.Column("signal_id", sa.Integer(), nullable=True),
        sa.Column("confidence_at_entry", sa.Float(), nullable=True),
        sa.Column("market_regime_at_entry", sa.String(length=30), nullable=True),
        sa.Column("exit_reason", sa.String(length=50), nullable=True),
        sa.Column("entry_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("holding_days", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_symbol", "trades", ["symbol"], unique=False)

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("outcome", sa.String(length=10), nullable=True),
        sa.Column("signal_reasons", sa.JSON(), nullable=True),
        sa.Column("what_worked", sa.Text(), nullable=True),
        sa.Column("what_failed", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("market_regime_at_entry", sa.String(length=30), nullable=True),
        sa.Column("sector_strength_at_entry", sa.String(length=20), nullable=True),
        sa.Column("news_sentiment_at_entry", sa.String(length=10), nullable=True),
        sa.Column("confidence_at_entry", sa.Float(), nullable=True),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("holding_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_entries_trade_id", "journal_entries", ["trade_id"], unique=False)

    op.create_table(
        "option_chain_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("underlying", sa.String(length=20), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spot", sa.Float(), nullable=False),
        sa.Column("atm_strike", sa.Float(), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("strike_window", sa.Float(), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("near_call_oi", sa.Float(), nullable=False),
        sa.Column("near_put_oi", sa.Float(), nullable=False),
        sa.Column("near_spot_pcr", sa.Float(), nullable=True),
        sa.Column("atm_iv", sa.Float(), nullable=True),
        sa.Column("iv_skew_25d", sa.Float(), nullable=True),
        sa.Column("gex_per_1pct", sa.Float(), nullable=True),
        sa.Column("data_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_option_chain_snapshots_underlying", "option_chain_snapshots", ["underlying"], unique=False)
    op.create_index("ix_option_chain_snapshots_expiry", "option_chain_snapshots", ["expiry"], unique=False)
    op.create_index("ix_option_chain_snapshots_captured_at", "option_chain_snapshots", ["captured_at"], unique=False)
    op.create_index("ix_option_chain_snapshots_data_version", "option_chain_snapshots", ["data_version"], unique=False)

    op.create_table(
        "futures_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("underlying", sa.String(length=20), nullable=False),
        sa.Column("contract_symbol", sa.String(length=80), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ltp", sa.Float(), nullable=False),
        sa.Column("spot", sa.Float(), nullable=False),
        sa.Column("basis", sa.Float(), nullable=False),
        sa.Column("basis_pct", sa.Float(), nullable=False),
        sa.Column("open_interest", sa.Float(), nullable=False),
        sa.Column("oi_change", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("volume_change", sa.Float(), nullable=True),
        sa.Column("price_change", sa.Float(), nullable=True),
        sa.Column("cvd_proxy", sa.Float(), nullable=False),
        sa.Column("data_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_futures_snapshots_underlying", "futures_snapshots", ["underlying"], unique=False)
    op.create_index("ix_futures_snapshots_captured_at", "futures_snapshots", ["captured_at"], unique=False)
    op.create_index("ix_futures_snapshots_data_version", "futures_snapshots", ["data_version"], unique=False)

    op.create_table(
        "prediction_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("underlying", sa.String(length=20), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("spot", sa.Float(), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("session_label", sa.String(length=40), nullable=False),
        sa.Column("is_expiry_day", sa.Boolean(), nullable=False),
        sa.Column("scorer_version", sa.String(length=40), nullable=False),
        sa.Column(
            "data_version",
            sa.String(length=40),
            server_default="v0_pre_fix",
            nullable=False,
        ),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("factor_scores", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("cluster_scores", sa.JSON(), nullable=True),
        sa.Column("regime", sa.JSON(), nullable=True),
        sa.Column("shadow_features", sa.JSON(), nullable=True),
        sa.Column("contract_symbol", sa.String(length=80), nullable=True),
        sa.Column("contract_strike", sa.Float(), nullable=True),
        sa.Column("contract_option_type", sa.String(length=5), nullable=True),
        sa.Column("entry_premium", sa.Float(), nullable=True),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_status", sa.String(length=20), nullable=False),
        sa.Column("spot_15m", sa.Float(), nullable=True),
        sa.Column("spot_change_pct_15m", sa.Float(), nullable=True),
        sa.Column("direction_result_15m", sa.String(length=10), nullable=True),
        sa.Column("premium_15m", sa.Float(), nullable=True),
        sa.Column("premium_change_pct_15m", sa.Float(), nullable=True),
        sa.Column("net_pnl_15m", sa.Float(), nullable=True),
        sa.Column("spot_30m", sa.Float(), nullable=True),
        sa.Column("spot_change_pct_30m", sa.Float(), nullable=True),
        sa.Column("direction_result_30m", sa.String(length=10), nullable=True),
        sa.Column("premium_30m", sa.Float(), nullable=True),
        sa.Column("premium_change_pct_30m", sa.Float(), nullable=True),
        sa.Column("net_pnl_30m", sa.Float(), nullable=True),
        sa.Column("spot_60m", sa.Float(), nullable=True),
        sa.Column("spot_change_pct_60m", sa.Float(), nullable=True),
        sa.Column("direction_result_60m", sa.String(length=10), nullable=True),
        sa.Column("premium_60m", sa.Float(), nullable=True),
        sa.Column("premium_change_pct_60m", sa.Float(), nullable=True),
        sa.Column("net_pnl_60m", sa.Float(), nullable=True),
        sa.Column("outcomes_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prediction_logs_underlying", "prediction_logs", ["underlying"], unique=False)
    op.create_index("ix_prediction_logs_expiry", "prediction_logs", ["expiry"], unique=False)
    op.create_index("ix_prediction_logs_direction", "prediction_logs", ["direction"], unique=False)
    op.create_index("ix_prediction_logs_scorer_version", "prediction_logs", ["scorer_version"], unique=False)
    op.create_index("ix_prediction_logs_data_version", "prediction_logs", ["data_version"], unique=False)
    op.create_index("ix_prediction_logs_predicted_at", "prediction_logs", ["predicted_at"], unique=False)
    op.create_index("ix_prediction_logs_outcome_status", "prediction_logs", ["outcome_status"], unique=False)

    op.create_table(
        "premarket_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("overall_sentiment", sa.String(length=30), nullable=False),
        sa.Column("heuristic_confidence", sa.Float(), nullable=False),
        sa.Column("directional_score", sa.Float(), nullable=False),
        sa.Column("recommended_action", sa.String(length=20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_premarket_reports_report_date", "premarket_reports", ["report_date"], unique=True)

    op.create_table(
        "strategy_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy", sa.String(length=40), nullable=False),
        sa.Column("symbol", sa.String(length=40), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("signal_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("executed", sa.String(length=10), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_signals_strategy", "strategy_signals", ["strategy"], unique=False)
    op.create_index("ix_strategy_signals_symbol", "strategy_signals", ["symbol"], unique=False)
    op.create_index("ix_strategy_signals_session_date", "strategy_signals", ["session_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_strategy_signals_session_date", table_name="strategy_signals")
    op.drop_index("ix_strategy_signals_symbol", table_name="strategy_signals")
    op.drop_index("ix_strategy_signals_strategy", table_name="strategy_signals")
    op.drop_table("strategy_signals")

    op.drop_index("ix_premarket_reports_report_date", table_name="premarket_reports")
    op.drop_table("premarket_reports")

    op.drop_index("ix_prediction_logs_outcome_status", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_predicted_at", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_data_version", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_scorer_version", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_direction", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_expiry", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_underlying", table_name="prediction_logs")
    op.drop_table("prediction_logs")

    op.drop_index("ix_futures_snapshots_data_version", table_name="futures_snapshots")
    op.drop_index("ix_futures_snapshots_captured_at", table_name="futures_snapshots")
    op.drop_index("ix_futures_snapshots_underlying", table_name="futures_snapshots")
    op.drop_table("futures_snapshots")

    op.drop_index("ix_option_chain_snapshots_data_version", table_name="option_chain_snapshots")
    op.drop_index("ix_option_chain_snapshots_captured_at", table_name="option_chain_snapshots")
    op.drop_index("ix_option_chain_snapshots_expiry", table_name="option_chain_snapshots")
    op.drop_index("ix_option_chain_snapshots_underlying", table_name="option_chain_snapshots")
    op.drop_table("option_chain_snapshots")

    op.drop_index("ix_journal_entries_trade_id", table_name="journal_entries")
    op.drop_table("journal_entries")

    op.drop_index("ix_trades_symbol", table_name="trades")
    op.drop_table("trades")

    op.drop_index("ix_signals_symbol", table_name="signals")
    op.drop_table("signals")

    op.drop_index("ix_ohlcv_data_timestamp", table_name="ohlcv_data")
    op.drop_index("ix_ohlcv_data_symbol", table_name="ohlcv_data")
    op.drop_table("ohlcv_data")

    op.drop_table("stocks")
