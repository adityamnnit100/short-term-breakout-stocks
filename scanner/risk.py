"""Risk filter for avoiding overstretched names."""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from .config import ScannerConfig
from .indicators import atr


def calculate_risk_score(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, dict]:
    """Reject highly extended and volatile setups."""
    if df is None or df.empty or len(df) < config.min_candles:
        return 0.0, {"reason": "insufficient_data"}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    atr_series = atr(df, config.atr_window)
    if close.empty or atr_series.empty:
        return 0.0, {"reason": "missing_ohlc_data"}

    latest_close = float(close.iloc[-1])
    latest_atr = float(atr_series.iloc[-1])
    avg_atr = float(atr_series.tail(20).mean())
    if latest_atr <= 0:
        return 0.0, {"reason": "invalid_atr"}

    atr_pct = (latest_atr / latest_close) * 100.0
    score = 100.0
    if atr_pct > 4.5:
        score -= 50.0
    if avg_atr > 0 and latest_atr / avg_atr > 1.8:
        score -= 30.0
    if close.pct_change().tail(10).std() > 0.05:
        score -= 20.0

    metrics = {"atr_pct": round(atr_pct, 2), "latest_atr": round(latest_atr, 2)}
    return round(max(score, 0.0), 2), metrics
