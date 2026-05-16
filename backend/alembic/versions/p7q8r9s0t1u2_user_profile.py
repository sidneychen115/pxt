"""user profile: users, user_strategies, positions, user_id on signals/backtests"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p7q8r9s0t1u2"
down_revision: Union[str, None] = "o6p7q8r9s0t1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.execute("INSERT INTO users (username) VALUES ('cx'), ('cc')")

    op.create_table(
        "user_strategies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        sa.Column("symbols", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("timeframes", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("run_frequency", sa.String(length=50), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_symbols", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "strategy_id", name="uq_user_strategy"),
    )

    op.create_table(
        "user_positions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(16, 4), nullable=False, server_default="0"),
        sa.Column("avg_cost", sa.Numeric(16, 6), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "instrument_id"),
    )

    op.create_table(
        "position_fills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=True),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("quantity", sa.Numeric(16, 4), nullable=False),
        sa.Column("fill_price", sa.Numeric(16, 6), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["trade_signals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    for table in ("trade_signals", "backtests", "backtest_presets"):
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE trade_signals SET user_id = (SELECT id FROM users WHERE username = 'cc')
    """)
    op.execute("""
        UPDATE backtests SET user_id = (SELECT id FROM users WHERE username = 'cc')
    """)
    op.execute("""
        UPDATE backtest_presets SET user_id = (SELECT id FROM users WHERE username = 'cc')
    """)

    op.execute("""
        INSERT INTO user_strategies (
            user_id, strategy_id, symbols, timeframes, run_frequency,
            parameters, is_active, max_symbols, updated_at
        )
        SELECT u.id, s.id, s.symbols, s.timeframes, s.run_frequency,
               s.parameters, s.is_active, s.max_symbols, s.updated_at
        FROM strategies s
        CROSS JOIN users u
        WHERE u.username = 'cc'
    """)

    for table in ("trade_signals", "backtests", "backtest_presets"):
        op.alter_column(table, "user_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_user_id",
            table,
            "users",
            ["user_id"],
            ["id"],
        )

    op.create_index("idx_signals_user", "trade_signals", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_signals_user", table_name="trade_signals")
    for table in ("backtest_presets", "backtests", "trade_signals"):
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")
        op.drop_column(table, "user_id")
    op.drop_table("position_fills")
    op.drop_table("user_positions")
    op.drop_table("user_strategies")
    op.drop_table("users")
