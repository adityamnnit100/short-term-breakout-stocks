"""Trend filter logic for the momentum scanner."""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from .config import ScannerConfig
from .indicators import ema, pct_change


def calculate_trend_score(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, dict]:
    """Return the trend score and supporting metrics for a stock."""
    if df is None or df.empty or len(df) < config.min_candles:
        return 0.0, {"reason": "insufficient_data"}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        return 0.0, {"reason": "missing_close"}

    ema20 = ema(close, config.ema_fast)
    ema50 = ema(close, config.ema_medium)
    ema200 = ema(close, config.ema_slow)

    latest_close = float(close.iloc[-1])
    latest_ema20 = float(ema20.iloc[-1])
    latest_ema50 = float(ema50.iloc[-1])
    latest_ema200 = float(ema200.iloc[-1])

    price_above_ema20 = latest_close > latest_ema20
    ema20_above_ema50 = latest_ema20 > latest_ema50
    ema50_above_ema200 = latest_ema50 > latest_ema200
    ema200_slope_positive = float(ema200.iloc[-1] - ema200.iloc[-20]) > 0.0

    score = 0.0
    if price_above_ema20:
        score += 25.0
    if ema20_above_ema50:
        score += 25.0
    if ema50_above_ema200:
        score += 25.0
    if ema200_slope_positive:
        score += 25.0

    metrics = {
        "price_above_ema20": price_above_ema20,
        "ema20_above_ema50": ema20_above_ema50,
        "ema50_above_ema200": ema50_above_ema200,
        "ema200_slope_positive": ema200_slope_positive,
        "ema20": latest_ema20,
        "ema50": latest_ema50,
        "ema200": latest_ema200,
        "return_20d": pct_change(close, 20),
        "return_50d": pct_change(close, 50),
    }
    return round(score, 2), metrics
