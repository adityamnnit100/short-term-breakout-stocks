"""Volume-based filters for breakout and accumulation quality."""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from .config import ScannerConfig


def calculate_volume_score(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, dict]:
    """Score current volume relative to the recent historical average."""
    if df is None or df.empty or len(df) < config.min_candles:
        return 0.0, {"reason": "insufficient_data"}

    volume = pd.to_numeric(df["Volume"], errors="coerce").dropna()
    if volume.empty:
        return 0.0, {"reason": "missing_volume"}

    avg_volume = volume.rolling(config.volume_sma_window).mean().iloc[-1]
    current_volume = float(volume.iloc[-1])
    recent_low = float(volume.tail(config.volume_contraction_lookback).min())
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0
    contraction_pct = ((recent_low / avg_volume) - 1.0) * 100.0 if avg_volume > 0 else 0.0

    score = 0.0
    if volume_ratio >= config.volume_multiplier:
        score += 50.0
    elif volume_ratio >= 1.0:
        score += 25.0
    if contraction_pct <= -20.0:
        score += 25.0
    if volume_ratio >= 1.2:
        score += 25.0

    metrics = {
        "avg_volume": round(float(avg_volume), 2),
        "current_volume": round(current_volume, 2),
        "volume_ratio": round(volume_ratio, 2),
        "recent_low_volume": round(recent_low, 2),
        "contraction_pct": round(contraction_pct, 2),
    }
    return round(min(score, 100.0), 2), metrics
