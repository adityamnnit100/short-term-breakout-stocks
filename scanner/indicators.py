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


def vwap(df: pd.DataFrame) -> pd.Series:
    """Compute session VWAP for an intraday DataFrame.

    The function groups rows by calendar date (based on the index) and computes
    a cumulative VWAP per session: cumsum(tp*vol)/cumsum(vol).
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    try:
        tp = (pd.to_numeric(df["High"], errors="coerce") + pd.to_numeric(df["Low"], errors="coerce") + pd.to_numeric(df["Close"], errors="coerce")) / 3.0
        vol = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        tpv = tp * vol
        # group by session date
        groups = df.index.date
        cum_tpv = tpv.groupby(groups).cumsum()
        cum_vol = vol.groupby(groups).cumsum().replace({0.0: float("nan")})
        return cum_tpv / cum_vol
    except Exception:
        return pd.Series(dtype=float)


def relative_volume(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Relative volume (RVol): current volume divided by rolling mean volume.

    This is a simple, robust RVol proxy suitable for intraday and daily frames.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    try:
        vol = pd.to_numeric(df["Volume"], errors="coerce")
        avg = vol.rolling(window=window, min_periods=1).mean()
        return vol / avg.replace({0.0: float("nan")})
    except Exception:
        return pd.Series(dtype=float)


def intraday_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Alias for ATR computation tuned for intraday windows."""
    return atr(df, window)
