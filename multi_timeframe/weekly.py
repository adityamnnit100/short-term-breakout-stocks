"""Weekly timeframe confirmation scoring."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from scanner.config import ScannerConfig
from scanner.indicators import ema


def _weekly_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    frame = df.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if frame.empty:
        return frame
    if frame.index.inferred_freq and str(frame.index.inferred_freq).upper().startswith("W"):
        return frame
    return frame.resample("W-FRI").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()


def score_weekly_confirmation(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, Dict[str, float], List[str]]:
    """Return a 0-20 weekly confirmation score."""
    weekly = _weekly_frame(df)
    if weekly is None or weekly.empty or len(weekly) < 20:
        return 0.0, {"reason": "insufficient_weekly_data"}, []

    close = pd.to_numeric(weekly["Close"], errors="coerce").dropna()
    high = pd.to_numeric(weekly["High"], errors="coerce").dropna()
    low = pd.to_numeric(weekly["Low"], errors="coerce").dropna()
    if close.empty or high.empty or low.empty:
        return 0.0, {"reason": "missing_weekly_data"}, []

    ema20 = ema(close, config.ema_fast)
    ema50 = ema(close, config.ema_medium)

    latest_close = float(close.iloc[-1])
    latest_ema20 = float(ema20.iloc[-1])
    latest_ema50 = float(ema50.iloc[-1])

    score = 0.0
    reasons: List[str] = []
    if latest_close > latest_ema20:
        score += 5.0
        reasons.append("Weekly close above EMA20")
    if latest_close > latest_ema50:
        score += 5.0
        reasons.append("Weekly close above EMA50")
    if latest_ema20 > latest_ema50:
        score += 5.0
        reasons.append("Weekly EMA alignment bullish")

    weekly_highs = high.tail(6)
    weekly_lows = low.tail(6)
    higher_highs = int((weekly_highs.diff().dropna() > 0).sum())
    higher_lows = int((weekly_lows.diff().dropna() > 0).sum())
    if higher_highs >= 3:
        score += 2.5
        reasons.append("Weekly higher highs")
    elif higher_highs >= 2:
        score += 1.5
    if higher_lows >= 3:
        score += 2.5
        reasons.append("Weekly higher lows")
    elif higher_lows >= 2:
        score += 1.5

    metrics = {
        "weekly_close": round(latest_close, 2),
        "weekly_ema20": round(latest_ema20, 2),
        "weekly_ema50": round(latest_ema50, 2),
        "weekly_higher_highs": float(higher_highs),
        "weekly_higher_lows": float(higher_lows),
    }
    return round(min(score, 20.0), 2), metrics, reasons
