"""Candle tightness scoring."""

from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd


def score_candle_tightness(df: pd.DataFrame) -> Tuple[float, Dict[str, float]]:
    """Return a 0-15 score for tight candles and constructive patterns."""
    if df is None or df.empty or len(df) < 10:
        return 0.0, {"reason": "insufficient_data"}

    recent = df.tail(10).copy()
    open_ = pd.to_numeric(recent["Open"], errors="coerce")
    high = pd.to_numeric(recent["High"], errors="coerce")
    low = pd.to_numeric(recent["Low"], errors="coerce")
    close = pd.to_numeric(recent["Close"], errors="coerce")
    if open_.empty or high.empty or low.empty or close.empty:
        return 0.0, {"reason": "missing_ohlc"}

    body = (close - open_).abs()
    candle_range = (high - low).replace(0, pd.NA)
    body_ratio = float((body / candle_range).fillna(0).tail(5).mean())

    inside_bars = 0
    for idx in range(1, len(recent)):
        if high.iloc[idx] <= high.iloc[idx - 1] and low.iloc[idx] >= low.iloc[idx - 1]:
            inside_bars += 1

    nr7 = False
    nr4 = False
    if len(candle_range) >= 7:
        nr7 = float(candle_range.iloc[-1]) <= float(candle_range.tail(7).min())
    if len(candle_range) >= 4:
        nr4 = float(candle_range.iloc[-1]) <= float(candle_range.tail(4).min())

    tight_closes = int((close.diff().abs().tail(5) <= close.tail(5).std() * 0.5).sum())
    consecutive_tight = int(((body_ratio < 0.35) and (close.tail(3).max() - close.tail(3).min() <= close.tail(3).mean() * 0.015)))

    score = 0.0
    if body_ratio < 0.25:
        score += 5.0
    elif body_ratio < 0.35:
        score += 3.0

    if nr7:
        score += 4.0
    if nr4:
        score += 2.0
    score += min(inside_bars, 3) * 1.5
    score += min(tight_closes, 3) * 1.0
    if consecutive_tight:
        score += 2.0

    return round(min(score, 15.0), 2), {
        "body_ratio": round(float(body_ratio), 3),
        "inside_bars": float(inside_bars),
        "nr7": float(nr7),
        "nr4": float(nr4),
        "tight_closes": float(tight_closes),
        "consecutive_tight": float(consecutive_tight),
    }
