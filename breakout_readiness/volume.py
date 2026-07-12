"""Supply dry-up scoring."""

from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd


def score_volume_dryup(df: pd.DataFrame) -> Tuple[float, Dict[str, float]]:
    """Return a 0-15 score for sustained volume contraction."""
    if df is None or df.empty or len(df) < 20:
        return 0.0, {"reason": "insufficient_data"}

    volume = pd.to_numeric(df["Volume"], errors="coerce").dropna()
    if volume.empty or len(volume) < 20:
        return 0.0, {"reason": "missing_volume"}

    avg20 = float(volume.tail(20).mean())
    avg5 = float(volume.tail(5).mean())
    avg3 = float(volume.tail(3).mean())
    min20 = float(volume.tail(20).min())
    min5 = float(volume.tail(5).min())
    current = float(volume.iloc[-1])

    score = 0.0
    if avg5 < avg20 * 0.8:
        score += 4.0
    if avg3 < avg5 * 0.9:
        score += 4.0
    if current <= min5:
        score += 3.0
    if min20 < avg20 * 0.65:
        score += 4.0

    return round(min(score, 15.0), 2), {
        "volume_avg20": round(avg20, 2),
        "volume_avg5": round(avg5, 2),
        "volume_avg3": round(avg3, 2),
        "volume_min20": round(min20, 2),
        "volume_min5": round(min5, 2),
        "volume_current": round(current, 2),
    }
