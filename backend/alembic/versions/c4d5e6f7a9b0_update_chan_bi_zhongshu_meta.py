"""Update chan_bi_fractal_mvp display meta and merge new default parameters."""

from typing import Sequence, Union

from alembic import op

revision: str = "c4d5e6f7a9b0"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE strategies SET
            name = 'Chan MVP: 分型 + 笔 + 中枢 (daily OHLC)',
            description = 'Daily OHLC: inclusion, 分型, 笔 (min_fractal_sep), 最近 N 笔区间重叠之中枢；'
                '买：底分型确认 + 向下笔终点 + 收盘 > ZG；卖：顶分型 + 向上笔终点 + 可选收盘 < ZD；'
                '可选 SMA。非完备缠论。',
            parameters = COALESCE(parameters, '{}'::jsonb) || '{
                "use_sma_filter": false,
                "bar_limit": 320,
                "min_fractal_sep": 4,
                "use_bi_filter": true,
                "use_zhongshu_filter": true,
                "zhongshu_stroke_count": 3,
                "buy_close_above_zg": true,
                "sell_close_below_zd": true
            }'::jsonb
        WHERE id = 'chan_bi_fractal_mvp';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies SET
            name = 'Chan MVP: fractal confirm (daily OHLC)',
            description = 'Daily OHLC: K-line inclusion merge, strict fractals; buy on confirmed bottom (optional SMA filter), '
                'sell on confirmed top. Coarse Chan MVP for backtests.',
            parameters = COALESCE(parameters, '{}'::jsonb) || '{
                "use_sma_filter": true,
                "bar_limit": 240
            }'::jsonb
        WHERE id = 'chan_bi_fractal_mvp';
    """)
