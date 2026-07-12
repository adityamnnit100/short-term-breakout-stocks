"""Resistance and breakout-distance scoring."""

from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd


def _pivot_highs(high: pd.Series, lookback: int = 3) -> pd.Series:
    highs = pd.to_numeric(high, errors="coerce")
    if highs.empty:
        return highs
    pivots = []
    for idx in range(lookback, len(highs) - lookback):
        window = highs.iloc[idx - lookback : idx + lookback + 1]
        value = highs.iloc[idx]
        if pd.notna(value) and value >= window.max():
            pivots.append((highs.index[idx], float(value)))
    if not pivots:
        return pd.Series(dtype=float)
    return pd.Series(dict(pivots), dtype=float)


def score_breakout_distance(df: pd.DataFrame, current_price: float) -> Tuple[float, Dict[str, float]]:
    """Return a 0-20 score based on proximity to the nearest resistance."""
    if df is None or df.empty or current_price <= 0:
        return 0.0, {"reason": "insufficient_data"}

    recent = df.tail(120).copy()
    high = pd.to_numeric(recent["High"], errors="coerce")
    close = pd.to_numeric(recent["Close"], errors="coerce")
    if high.dropna().empty or close.dropna().empty:
        return 0.0, {"reason": "missing_ohlc"}

    candidates = [
        float(high.tail(20).max()),
        float(high.tail(50).max()),
        float(high.tail(100).max()),
    ]
    pivots = _pivot_highs(high.tail(60))
    candidates.extend(float(value) for value in pivots.tail(8).tolist() if pd.notna(value))
    candidates = sorted({c for c in candidates if c > 0})

    resistance = None
    for candidate in candidates:
        if candidate >= current_price:
            resistance = candidate
            break
    if resistance is None:
        resistance = max(candidates) if candidates else float(high.tail(20).max())

    resistance_gap_pct = ((resistance - current_price) / resistance * 100.0) if resistance > 0 else 0.0
    distance = max(resistance_gap_pct, 0.0)

    if distance < 1.0:
        score = 20.0
    elif distance < 3.0:
        score = 18.0
    elif distance < 5.0:
        score = 14.0
    elif distance < 8.0:
        score = 8.0
    elif distance < 12.0:
        score = 4.0
    else:
        score = 1.0

    tests = 0
    tolerance = resistance * 0.015
    for value in high.tail(60).dropna().tolist():
        if abs(value - resistance) <= tolerance:
            tests += 1

    if tests >= 3:
        score += 2.0
    elif tests == 2:
        score += 1.0

    return round(min(score, 20.0), 2), {
        "nearest_resistance": round(float(resistance), 2),
        "resistance_gap_pct": round(float(resistance_gap_pct), 2),
        "resistance_tests": float(tests),
    }
