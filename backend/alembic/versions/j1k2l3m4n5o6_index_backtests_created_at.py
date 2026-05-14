"""index backtests.created_at for list ordering

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-05-14

"""
from typing import Sequence, Union

from alembic import op


revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "i0j1k2l3m4n5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_backtests_created_at",
        "backtests",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_backtests_created_at", table_name="backtests")
