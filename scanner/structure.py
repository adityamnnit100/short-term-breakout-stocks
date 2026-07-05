"""Structure filter for consolidation and compression."""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from .config import ScannerConfig
from .indicators import atr


def calculate_structure_score(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, dict]:
    """Score compression and consolidation characteristics."""
    if df is None or df.empty or len(df) < config.min_candles:
        return 0.0, {"reason": "insufficient_data"}

    recent = df.tail(config.contraction_window).copy()
    close = pd.to_numeric(recent["Close"], errors="coerce")
    high = pd.to_numeric(recent["High"], errors="coerce")
    low = pd.to_numeric(recent["Low"], errors="coerce")
    if close.empty or high.empty or low.empty:
        return 0.0, {"reason": "missing_ohlc_data"}

    range_pct = ((high.max() - low.min()) / close.iloc[-1]) * 100.0
    atr_series = atr(recent, config.atr_window)
    recent_atr = float(atr_series.iloc[-1]) if not atr_series.empty else float("nan")
    avg_atr = float(atr_series.mean()) if not atr_series.empty else float("nan")
    atr_contraction = 0.0 if pd.isna(avg_atr) or avg_atr <= 0 else ((recent_atr / avg_atr) * 100.0) - 100.0

    score = 0.0
    if range_pct < 15.0:
        score += 40.0
    if atr_contraction < -10.0:
        score += 35.0
    if recent["Close"].pct_change().abs().tail(5).mean() < 0.03:
        score += 25.0

    metrics = {
        "range_pct": round(range_pct, 2),
        "atr_contraction_pct": round(atr_contraction, 2),
        "recent_close_change": round(float(recent["Close"].pct_change().tail(5).mean()) * 100.0, 2),
    }
    return round(min(score, 100.0), 2), metrics
