"""Volatility and volume scoring for market regime analysis."""

from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd

from scanner.config import ScannerConfig
from scanner.indicators import atr


def score_market_volatility(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, Dict[str, float]]:
    """Score market volatility conditions on a 0-100 scale."""
    if df is None or df.empty or len(df) < config.market_regime_atr_window + 5:
        return 0.0, {"reason": "insufficient_data"}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        return 0.0, {"reason": "missing_close"}

    atr_series = atr(df, config.market_regime_atr_window)
    recent_atr = float(atr_series.tail(5).mean()) if not atr_series.empty else 0.0
    prior_atr = float(atr_series.tail(20).head(10).mean()) if len(atr_series) >= 20 else float(atr_series.mean()) if not atr_series.empty else 0.0
    atr_change_pct = ((recent_atr / prior_atr) - 1.0) * 100.0 if prior_atr > 0 else 0.0

    avg_daily_range = float((pd.to_numeric(df["High"], errors="coerce") - pd.to_numeric(df["Low"], errors="coerce")).tail(20).mean())
    prior_daily_range = float((pd.to_numeric(df["High"], errors="coerce") - pd.to_numeric(df["Low"], errors="coerce")).tail(40).head(20).mean()) if len(df) >= 40 else avg_daily_range
    adr_change_pct = ((avg_daily_range / prior_daily_range) - 1.0) * 100.0 if prior_daily_range > 0 else 0.0

    score = 100.0
    high = float(config.market_regime_volatility_high_threshold_pct)
    mid = float(config.market_regime_volatility_mid_threshold_pct)
    if atr_change_pct > high or adr_change_pct > high:
        score = 20.0
    elif atr_change_pct > mid or adr_change_pct > mid:
        score = 45.0
    elif atr_change_pct > 0 or adr_change_pct > 0:
        score = 70.0

    metrics = {
        "atr_change_pct": round(float(atr_change_pct), 2),
        "adr_change_pct": round(float(adr_change_pct), 2),
        "recent_atr": round(float(recent_atr), 2),
        "avg_daily_range": round(float(avg_daily_range), 2),
    }
    return round(min(max(score, 0.0), 100.0), 2), metrics


def score_market_volume(df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, Dict[str, float]]:
    """Score accumulation or distribution on a 0-100 scale."""
    if df is None or df.empty or len(df) < config.market_regime_volume_window + 5:
        return 0.0, {"reason": "insufficient_data"}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    volume = pd.to_numeric(df["Volume"], errors="coerce").dropna()
    if close.empty or volume.empty:
        return 0.0, {"reason": "missing_data"}

    recent_volume = float(volume.tail(config.market_regime_volume_window).mean())
    prior_volume = float(volume.tail(config.market_regime_volume_window * 2).head(config.market_regime_volume_window).mean())
    volume_trend_pct = ((recent_volume / prior_volume) - 1.0) * 100.0 if prior_volume > 0 else 0.0

    changes = close.pct_change().fillna(0.0) * 100.0
    vols = volume.pct_change().fillna(0.0)
    distribution_days = int(((changes < -0.2) & (vols > 0)).tail(20).sum())
    accumulation_days = int(((changes > 0.2) & (vols > 0)).tail(20).sum())

    edge = int(config.market_regime_accumulation_edge_days)
    if accumulation_days > distribution_days + edge:
        score = 100.0
    elif accumulation_days > distribution_days:
        score = 80.0
    elif accumulation_days == distribution_days:
        score = 60.0
    elif distribution_days <= accumulation_days + int(config.market_regime_distribution_edge_days):
        score = 40.0
    else:
        score = 20.0

    if volume_trend_pct < -float(config.market_regime_volume_trend_threshold_pct):
        score = min(100.0, score + 5.0)
    elif volume_trend_pct > float(config.market_regime_volume_trend_threshold_pct):
        score = max(0.0, score - 10.0)

    metrics = {
        "volume_trend_pct": round(float(volume_trend_pct), 2),
        "distribution_days": float(distribution_days),
        "accumulation_days": float(accumulation_days),
        "recent_volume": round(float(recent_volume), 2),
        "prior_volume": round(float(prior_volume), 2),
    }
    return round(min(max(score, 0.0), 100.0), 2), metrics
