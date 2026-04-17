import pandas as pd
import pandas_ta as ta


class Indicators:
    """Thin wrapper around pandas-ta. All methods accept a DataFrame with a 'close' column."""

    @staticmethod
    def _validate(df: pd.DataFrame, *required: str) -> None:
        if df.empty:
            raise ValueError("Indicators received an empty DataFrame")
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

    @staticmethod
    def sma(df: pd.DataFrame, period: int) -> pd.Series:
        Indicators._validate(df, "close")
        return ta.sma(df["close"], length=period)

    @staticmethod
    def ema(df: pd.DataFrame, period: int) -> pd.Series:
        Indicators._validate(df, "close")
        return ta.ema(df["close"], length=period)

    @staticmethod
    def macd(
        df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        Indicators._validate(df, "close")
        result = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
        return result  # columns: MACD_f_s_sig, MACDh_f_s_sig, MACDs_f_s_sig

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        Indicators._validate(df, "close")
        return ta.rsi(df["close"], length=period)

    @staticmethod
    def bbands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
        # columns: BBL_p_s, BBM_p_s, BBU_p_s, BBB_p_s, BBP_p_s
        Indicators._validate(df, "close")
        return ta.bbands(df["close"], length=period, std=std)

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        Indicators._validate(df, "high", "low", "close")
        return ta.atr(df["high"], df["low"], df["close"], length=period)

    @staticmethod
    def stoch(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
        Indicators._validate(df, "high", "low", "close")
        return ta.stoch(df["high"], df["low"], df["close"], k=k, d=d)

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        Indicators._validate(df, "high", "low", "close")
        return ta.adx(df["high"], df["low"], df["close"], length=period)
