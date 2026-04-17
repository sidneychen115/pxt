import pandas as pd
import pandas_ta as ta


class Indicators:
    """Thin wrapper around pandas-ta. All methods accept a DataFrame with a 'close' column."""

    @staticmethod
    def sma(df: pd.DataFrame, period: int) -> pd.Series:
        return ta.sma(df["close"], length=period)

    @staticmethod
    def ema(df: pd.DataFrame, period: int) -> pd.Series:
        return ta.ema(df["close"], length=period)

    @staticmethod
    def macd(
        df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        result = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
        return result  # columns: MACD_f_s_sig, MACDh_f_s_sig, MACDs_f_s_sig

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        return ta.rsi(df["close"], length=period)

    @staticmethod
    def bbands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
        return ta.bbands(df["close"], length=period, std=std)
        # columns: BBL_p_s, BBM_p_s, BBU_p_s, BBB_p_s, BBP_p_s

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        return ta.atr(df["high"], df["low"], df["close"], length=period)

    @staticmethod
    def stoch(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
        return ta.stoch(df["high"], df["low"], df["close"], k=k, d=d)

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        return ta.adx(df["high"], df["low"], df["close"], length=period)
