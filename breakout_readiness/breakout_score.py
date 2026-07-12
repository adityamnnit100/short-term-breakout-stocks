"""Final breakout pressure and readiness aggregation."""

from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd


def score_breakout_pressure(df: pd.DataFrame) -> Tuple[float, Dict[str, float]]:
    """Return a 0-10 score for higher lows, repeated tests, and compression."""
    if df is None or df.empty or len(df) < 20:
        return 0.0, {"reason": "insufficient_data"}

    recent = df.tail(60).copy()
    close = pd.to_numeric(recent["Close"], errors="coerce").dropna()
    high = pd.to_numeric(recent["High"], errors="coerce").dropna()
    low = pd.to_numeric(recent["Low"], errors="coerce").dropna()
    if close.empty or high.empty or low.empty:
        return 0.0, {"reason": "missing_ohlc"}

    higher_lows = int((low.tail(5).diff().dropna() > 0).sum())
    repeated_tests = 0
    resistance = float(high.tail(20).max())
    tolerance = resistance * 0.0125
    for value in high.tail(40).dropna().tolist():
        if abs(value - resistance) <= tolerance:
            repeated_tests += 1

    last_highs = high.tail(10)
    last_lows = low.tail(10)
    ascending_triangle = bool(
        len(last_highs) >= 5
        and len(last_lows) >= 5
        and last_lows.iloc[-1] > last_lows.iloc[0]
        and last_highs.max() - last_highs.min() <= resistance * 0.03
    )
    compression = bool(close.tail(10).std() <= close.tail(30).std() * 0.8 if len(close) >= 30 else False)

    score = 0.0
    score += min(higher_lows, 4) * 1.5
    score += min(repeated_tests, 4) * 0.75
    if ascending_triangle:
        score += 3.0
    if compression:
        score += 1.5

    return round(min(score, 10.0), 2), {
        "higher_lows": float(higher_lows),
        "repeated_tests": float(repeated_tests),
        "ascending_triangle": float(ascending_triangle),
        "compression": float(compression),
    }


def aggregate_breakout_readiness(
    compression_score: float,
    breakout_distance_score: float,
    volume_dryup_score: float,
    candle_tightness_score: float,
    rs_acceleration_score: float,
    breakout_pressure_score: float,
) -> Tuple[float, float]:
    """Combine module scores into a 0-100 readiness score with a small confluence bonus."""
    module_total = (
        compression_score
        + breakout_distance_score
        + volume_dryup_score
        + candle_tightness_score
        + rs_acceleration_score
        + breakout_pressure_score
    )
    thresholds = {
        "compression": 15.0,
        "distance": 12.0,
        "volume": 9.0,
        "candle": 9.0,
        "rs": 6.0,
        "pressure": 6.0,
    }
    strong_modules = sum(
        [
            compression_score >= thresholds["compression"],
            breakout_distance_score >= thresholds["distance"],
            volume_dryup_score >= thresholds["volume"],
            candle_tightness_score >= thresholds["candle"],
            rs_acceleration_score >= thresholds["rs"],
            breakout_pressure_score >= thresholds["pressure"],
        ]
    )
    confluence_bonus = min(5.0, strong_modules * 1.5)
    return round(min(module_total + confluence_bonus, 100.0), 2), round(confluence_bonus, 2)
