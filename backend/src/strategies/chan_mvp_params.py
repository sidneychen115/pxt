"""Timeframe-aware defaults for Chan MVP (分型 / 笔 / 中枢)."""

from __future__ import annotations

# Shared toggles; bar counts scale with bar length.
_CHAN_MVP_SHARED_DEFAULTS: dict[str, object] = {
    "use_sma_filter": False,
    "use_bi_filter": True,
    "use_zhongshu_filter": True,
    "zhongshu_stroke_count": 3,
    "buy_close_above_zg": True,
    "sell_close_below_zd": False,
}

_CHAN_MVP_BY_TIMEFRAME: dict[str, dict[str, object]] = {
    "1d": {
        "timeframe": "1d",
        "bar_limit": 320,
        "min_fractal_sep": 4,
        "sma_period": 20,
    },
    "1h": {
        "timeframe": "1h",
        # ~6.5 RTH bars/day × ~230 sessions ≈ 1500 hourly bars
        "bar_limit": 1500,
        "min_fractal_sep": 4,
        "sma_period": 50,
        # yfinance 1h history ~730d total; keep warmup modest vs default 24m for daily.
        "backtest_warmup_months": 6,
    },
    "4h": {
        "timeframe": "4h",
        "bar_limit": 1200,
        "min_fractal_sep": 4,
        "sma_period": 50,
        "backtest_warmup_months": 6,
    },
    "15m": {
        "timeframe": "15m",
        # yfinance 15m ~60d; ~26 RTH bars/day × 60 ≈ 1560 bars max
        "bar_limit": 800,
        "min_fractal_sep": 4,
        "sma_period": 50,
        "backtest_warmup_months": 0,
    },
    "5m": {
        "timeframe": "5m",
        "bar_limit": 1200,
        "min_fractal_sep": 4,
        "sma_period": 50,
        "backtest_warmup_months": 0,
    },
    "30m": {
        "timeframe": "30m",
        "bar_limit": 800,
        "min_fractal_sep": 4,
        "sma_period": 50,
        "backtest_warmup_months": 0,
    },
}

# Unknown intraday TFs inherit the closest template (never downgrade to 1d).
_CHAN_MVP_TEMPLATE_FALLBACK: dict[str, str] = {
    "1m": "5m",
}

DEFAULT_CHAN_MVP_TIMEFRAME = "1h"


def chan_mvp_default_parameters(timeframe: str = DEFAULT_CHAN_MVP_TIMEFRAME) -> dict[str, object]:
    tf = timeframe if timeframe in _CHAN_MVP_BY_TIMEFRAME else "1d"
    return {**_CHAN_MVP_SHARED_DEFAULTS, **_CHAN_MVP_BY_TIMEFRAME[tf]}


def chan_mvp_template_timeframe(timeframe: str) -> str:
    """Default-parameter template for ``timeframe`` (preserves user TF in merged output)."""
    if timeframe in _CHAN_MVP_BY_TIMEFRAME:
        return timeframe
    return _CHAN_MVP_TEMPLATE_FALLBACK.get(timeframe, "1d")


def resolve_chan_mvp_params(parameters: dict | None) -> dict:
    """Merge user parameters with timeframe-specific defaults (explicit user keys win)."""
    raw = parameters or {}
    user_tf = str(raw.get("timeframe") or DEFAULT_CHAN_MVP_TIMEFRAME)
    template_tf = chan_mvp_template_timeframe(user_tf)
    base = chan_mvp_default_parameters(template_tf)
    merged = {**base, **raw}
    merged["timeframe"] = user_tf
    # Re-apply per-TF defaults only for keys the user did not supply.
    for key, val in _CHAN_MVP_BY_TIMEFRAME[template_tf].items():
        if key == "timeframe":
            continue
        if key not in raw:
            merged[key] = val
    for key, val in _CHAN_MVP_SHARED_DEFAULTS.items():
        if key not in raw:
            merged[key] = val
    return merged
