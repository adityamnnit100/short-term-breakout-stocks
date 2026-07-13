"""Indicator calculations shared across scanner modules."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def atr(df: pd.DataFrame, window: int) -> pd.Series:
    high_low = pd.to_numeric(df["High"], errors="coerce") - pd.to_numeric(df["Low"], errors="coerce")
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=window).mean()


def rolling_volatility(series: pd.Series, window: int) -> pd.Series:
    return series.pct_change().rolling(window=window).std()


def pct_change(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        return float("nan")
    return (series.iloc[-1] / series.iloc[-1 - periods] - 1.0) * 100.0


def safe_pct_change(current: float, reference: float) -> float:
    if reference is None or reference <= 0:
        return 0.0
    return ((current / reference) - 1.0) * 100.0
