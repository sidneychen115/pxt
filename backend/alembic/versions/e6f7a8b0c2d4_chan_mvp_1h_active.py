"""chan_bi_fractal_mvp: enable 1h live/backtest defaults and activate."""

from typing import Sequence, Union

from alembic import op

revision: str = "e6f7a8b0c2d4"
down_revision: Union[str, None] = "d5e6f7a8b9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHAN_1H_PARAMS = """{
    "timeframe": "1h",
    "bar_limit": 1500,
    "min_fractal_sep": 4,
    "sma_period": 50,
    "use_sma_filter": false,
    "use_bi_filter": true,
    "use_zhongshu_filter": true,
    "zhongshu_stroke_count": 3,
    "buy_close_above_zg": true,
    "sell_close_below_zd": false
}"""


def upgrade() -> None:
    op.execute(f"""
        UPDATE strategies SET
            name = 'Chan MVP: 分型 + 笔 + 中枢 (1h / 日线)',
            description = 'OHLC 1h（默认）或日线：包含、分型、笔、简化中枢。'
                '买：底分型+向下笔+可选收>ZG；卖：顶分型+向上笔；可选 SMA。'
                '回测/实盘请在 parameters 中设 timeframe 为 1h 或 1d。',
            is_active = true,
            timeframes = ARRAY['1h', '1d'],
            run_frequency = '60m',
            parameters = COALESCE(parameters, '{{}}'::jsonb) || '{_CHAN_1H_PARAMS}'::jsonb,
            updated_at = now()
        WHERE id = 'chan_bi_fractal_mvp';
    """)
    op.execute(f"""
        UPDATE user_strategies SET
            is_active = true,
            timeframes = ARRAY['1h', '1d'],
            run_frequency = '60m',
            parameters = COALESCE(parameters, '{{}}'::jsonb) || '{_CHAN_1H_PARAMS}'::jsonb,
            updated_at = now()
        WHERE strategy_id = 'chan_bi_fractal_mvp';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies SET
            name = 'Chan MVP: 分型 + 笔 + 中枢 (daily OHLC)',
            description = 'Daily OHLC: inclusion, 分型, 笔, 三笔重叠之中枢。买：底分型+向下笔+收>ZG。'
                '卖默认：顶分型+向上笔（不要求破 ZD，否则极易整段回测仅一笔并在结束时平仓）。'
                '可选 sell_close_below_zd=true 收紧卖点；可选 SMA。',
            is_active = false,
            timeframes = ARRAY['1d'],
            run_frequency = '0 16 * * 1-5',
            parameters = COALESCE(parameters, '{}'::jsonb) || '{
                "timeframe": "1d",
                "bar_limit": 320,
                "sma_period": 20
            }'::jsonb,
            updated_at = now()
        WHERE id = 'chan_bi_fractal_mvp';
    """)
    op.execute("""
        UPDATE user_strategies SET
            timeframes = ARRAY['1d'],
            run_frequency = '0 16 * * 1-5',
            parameters = COALESCE(parameters, '{}'::jsonb) || '{
                "timeframe": "1d",
                "bar_limit": 320,
                "sma_period": 20
            }'::jsonb,
            updated_at = now()
        WHERE strategy_id = 'chan_bi_fractal_mvp';
    """)
