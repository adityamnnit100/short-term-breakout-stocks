"""Relative strength acceleration scoring."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd


def score_rs_acceleration(df: pd.DataFrame, benchmark: pd.DataFrame = None) -> Tuple[float, Dict[str, float]]:
    """Return a 0-10 score for accelerating relative strength."""
    if df is None or df.empty or len(df) < 30:
        return 0.0, {"reason": "insufficient_data"}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        return 0.0, {"reason": "missing_close"}

    if benchmark is not None and not benchmark.empty and "Close" in benchmark.columns:
        bench = pd.to_numeric(benchmark["Close"], errors="coerce").dropna()
        aligned = pd.concat([close, bench], axis=1, join="inner").dropna()
        if len(aligned) >= 30:
            ratio = aligned.iloc[:, 0] / aligned.iloc[:, 1].replace(0, np.nan)
        else:
            ratio = close.pct_change().fillna(0).cumsum()
    else:
        ratio = close.pct_change().fillna(0).cumsum()

    if len(ratio) < 20:
        return 0.0, {"reason": "insufficient_ratio_data"}

    r5 = float(ratio.tail(5).mean())
    r10 = float(ratio.tail(10).mean())
    r20 = float(ratio.tail(20).mean())
    slope_short = r5 - r10
    slope_long = r10 - r20
    accel = slope_short - slope_long

    score = 0.0
    if r5 > r10 > r20:
        score += 4.0
    if accel > 0:
        score += min(4.0, abs(accel) * 120.0)
    if r5 > 0 and r10 > 0:
        score += 2.0

    metrics = {
        "rs_ratio_5": round(r5, 4),
        "rs_ratio_10": round(r10, 4),
        "rs_ratio_20": round(r20, 4),
        "rs_acceleration": round(float(accel), 6),
    }
    return round(min(score, 10.0), 2), metrics
