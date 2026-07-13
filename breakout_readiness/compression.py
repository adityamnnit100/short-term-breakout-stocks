"""Compression scoring for volatility contraction."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from scanner.indicators import atr, safe_pct_change


def score_compression(df: pd.DataFrame) -> Tuple[float, Dict[str, float]]:
    """Return a 0-25 compression score plus supporting metrics."""
    if df is None or df.empty or len(df) < 30:
        return 0.0, {"reason": "insufficient_data"}

    recent = df.tail(30).copy()
    close = pd.to_numeric(recent["Close"], errors="coerce").dropna()
    high = pd.to_numeric(recent["High"], errors="coerce")
    low = pd.to_numeric(recent["Low"], errors="coerce")
    if close.empty or high.dropna().empty or low.dropna().empty:
        return 0.0, {"reason": "missing_ohlc"}

    atr_series = atr(recent, 14)
    atr_recent = float(atr_series.tail(5).mean()) if not atr_series.empty else 0.0
    atr_prior = float(atr_series.head(max(len(atr_series) - 5, 1)).tail(10).mean()) if len(atr_series) > 10 else float(atr_series.mean()) if not atr_series.empty else 0.0
    atr_contraction_pct = safe_pct_change(atr_recent, atr_prior)

    bb_mean = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bbw = ((bb_std * 4.0) / bb_mean.replace(0, np.nan)) * 100.0
    bbw_recent = float(bbw.tail(5).mean()) if not bbw.empty else 0.0
    bbw_prior = float(bbw.head(max(len(bbw) - 5, 1)).tail(10).mean()) if len(bbw) > 10 else float(bbw.mean()) if not bbw.empty else 0.0
    bbw_contraction_pct = safe_pct_change(bbw_recent, bbw_prior)

    recent_std = float(close.tail(10).std() or 0.0)
    prior_std = float(close.tail(30).std() or 0.0)
    std_contraction_pct = safe_pct_change(recent_std, prior_std)

    candle_ranges = (high - low).dropna()
    recent_range = float(candle_ranges.tail(5).mean()) if not candle_ranges.empty else 0.0
    prior_range = float(candle_ranges.tail(20).mean()) if len(candle_ranges) >= 20 else float(candle_ranges.mean()) if not candle_ranges.empty else 0.0
    range_contraction_pct = safe_pct_change(recent_range, prior_range)

    score = 0.0
    if atr_contraction_pct <= -10:
        score += 8.0
    elif atr_contraction_pct <= -5:
        score += 4.0

    if bbw_contraction_pct <= -10:
        score += 8.0
    elif bbw_contraction_pct <= -5:
        score += 4.0

    if std_contraction_pct <= -10:
        score += 4.0
    elif std_contraction_pct <= -5:
        score += 2.0

    if range_contraction_pct <= -10:
        score += 5.0
    elif range_contraction_pct <= -5:
        score += 2.5

    return round(min(score, 25.0), 2), {
        "atr_contraction_pct": round(float(atr_contraction_pct), 2),
        "bbw_contraction_pct": round(float(bbw_contraction_pct), 2),
        "std_contraction_pct": round(float(std_contraction_pct), 2),
        "range_contraction_pct": round(float(range_contraction_pct), 2),
    }
