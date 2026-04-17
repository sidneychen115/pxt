import pytest
import pandas as pd
import numpy as np
from src.strategies.indicators import Indicators


@pytest.fixture
def sample_df():
    n = 100
    rng = np.random.default_rng(42)
    prices = 100 + rng.standard_normal(n).cumsum()
    return pd.DataFrame({
        "open": prices * 0.99,
        "high": prices * 1.01,
        "low": prices * 0.98,
        "close": prices,
        "volume": rng.integers(1000, 10000, n),
    })


def test_sma_length(sample_df):
    result = Indicators.sma(sample_df, 10)
    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_df)
    assert result.iloc[:9].isna().all()   # first 9 are NaN
    assert not pd.isna(result.iloc[9])


def test_ema_length(sample_df):
    result = Indicators.ema(sample_df, 20)
    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_df)


def test_macd_columns(sample_df):
    result = Indicators.macd(sample_df)
    assert isinstance(result, pd.DataFrame)
    assert result.shape[1] == 3


def test_rsi_range(sample_df):
    result = Indicators.rsi(sample_df, 14)
    valid = result.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_bbands_columns(sample_df):
    result = Indicators.bbands(sample_df, 20)
    assert isinstance(result, pd.DataFrame)
    assert result.shape[1] == 5


def test_atr_length(sample_df):
    result = Indicators.atr(sample_df, 14)
    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_df)


def test_stoch_columns(sample_df):
    result = Indicators.stoch(sample_df)
    assert isinstance(result, pd.DataFrame)
    assert result.shape[1] >= 2


def test_adx_columns(sample_df):
    result = Indicators.adx(sample_df)
    assert isinstance(result, pd.DataFrame)
    assert result.shape[1] >= 1


def test_indicators_empty_dataframe_raises():
    import pytest
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    with pytest.raises(ValueError, match="empty"):
        Indicators.sma(empty, 10)


def test_indicators_missing_column_raises():
    import pytest
    df_no_close = pd.DataFrame({"open": [1.0, 2.0], "high": [2.0, 3.0]})
    with pytest.raises(ValueError, match="missing"):
        Indicators.sma(df_no_close, 5)
