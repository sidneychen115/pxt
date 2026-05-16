"""chan_bi_fractal_mvp: default sell_close_below_zd false (avoid holding to EoB only)."""

from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c1"
down_revision: Union[str, None] = "c4d5e6f7a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE strategies SET
            description = 'Daily OHLC: inclusion, 分型, 笔, 三笔重叠之中枢。买：底分型+向下笔+收>ZG。'
                '卖默认：顶分型+向上笔（不要求破 ZD，否则极易整段回测仅一笔并在结束时平仓）。'
                '可选 sell_close_below_zd=true 收紧卖点；可选 SMA。',
            parameters = COALESCE(parameters, '{}'::jsonb) || '{"sell_close_below_zd": false}'::jsonb
        WHERE id = 'chan_bi_fractal_mvp';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies SET
            parameters = COALESCE(parameters, '{}'::jsonb) || '{"sell_close_below_zd": true}'::jsonb
        WHERE id = 'chan_bi_fractal_mvp';
    """)
