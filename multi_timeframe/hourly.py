"""Hourly entry timing scoring."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from scanner.config import ScannerConfig
from scanner.indicators import ema


def score_hourly_entry_timing(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, Dict[str, float], List[str]]:
    """Return a 0-30 timing score from 1H data."""
    if df is None or df.empty or len(df) < 30:
        return 0.0, {"reason": "insufficient_hourly_data"}, []

    frame = df.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if frame.empty:
        return 0.0, {"reason": "missing_hourly_data"}, []

    close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
    high = pd.to_numeric(frame["High"], errors="coerce").dropna()
    low = pd.to_numeric(frame["Low"], errors="coerce").dropna()
    volume = pd.to_numeric(frame["Volume"], errors="coerce").dropna()
    if close.empty or high.empty or low.empty or volume.empty:
        return 0.0, {"reason": "missing_hourly_data"}, []

    ema_fast = ema(close, config.mtf_hourly_ema_fast)
    ema_slow = ema(close, config.mtf_hourly_ema_slow)
    latest_close = float(close.iloc[-1])
    latest_ema_fast = float(ema_fast.iloc[-1])
    latest_ema_slow = float(ema_slow.iloc[-1])
    current_volume = float(volume.iloc[-1])
    avg_volume = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0

    score = 0.0
    reasons: List[str] = []
    recent_high = float(high.tail(10).max())
    recent_low = float(low.tail(10).min())
    if latest_close > latest_ema_fast:
        score += 6.0
        reasons.append("1H close above EMA fast")
    if latest_ema_fast > latest_ema_slow:
        score += 5.0
        reasons.append("1H EMA alignment bullish")
    if latest_close >= recent_high * 0.995:
        score += 6.0
        reasons.append("1H breakout candle")
    elif latest_close >= latest_ema_fast * 0.995 and latest_close <= recent_high:
        score += 4.0
        reasons.append("1H constructive pullback")

    if volume_ratio >= 1.5:
        score += 5.0
        reasons.append("1H volume expansion")
    elif volume_ratio >= 1.0:
        score += 3.0
        reasons.append("1H volume stable")

    higher_lows = int((low.tail(6).diff().dropna() > 0).sum())
    if higher_lows >= 3:
        score += 4.0
        reasons.append("1H higher lows")
    elif higher_lows >= 2:
        score += 2.0

    tight_range = float((high.tail(10).max() - low.tail(10).min()) / max(latest_close, 1e-9) * 100.0)
    if tight_range <= 3.0:
        score += 4.0
        reasons.append("1H tight consolidation")
    elif tight_range <= 5.0:
        score += 2.0

    metrics = {
        "hourly_volume_ratio": round(float(volume_ratio), 2),
        "hourly_tight_range_pct": round(float(tight_range), 2),
        "hourly_ema_fast": round(float(latest_ema_fast), 2),
        "hourly_ema_slow": round(float(latest_ema_slow), 2),
        "hourly_recent_low": round(float(recent_low), 2),
    }
    return round(min(score, 30.0), 2), metrics, reasons
