"""Market regime scoring and classification."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from scanner.config import ScannerConfig
from scanner.indicators import ema, pct_change


def score_market_trend(index_df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, Dict[str, float], List[str]]:
    """Score the index trend on a 0-100 scale."""
    if index_df is None or index_df.empty or len(index_df) < config.ema_slow:
        return 0.0, {"reason": "insufficient_data"}, []

    close = pd.to_numeric(index_df["Close"], errors="coerce").dropna()
    if close.empty or len(close) < config.ema_slow:
        return 0.0, {"reason": "missing_close"}, []

    ema20 = ema(close, config.ema_fast)
    ema50 = ema(close, config.ema_medium)
    ema200 = ema(close, config.ema_slow)

    latest_close = float(close.iloc[-1])
    latest_ema20 = float(ema20.iloc[-1])
    latest_ema50 = float(ema50.iloc[-1])
    latest_ema200 = float(ema200.iloc[-1])

    trend_score = 0.0
    reasons: List[str] = []
    if latest_close > latest_ema20:
        trend_score += 25.0
        reasons.append("Price above EMA20")
    if latest_close > latest_ema50:
        trend_score += 25.0
        reasons.append("Price above EMA50")
    if latest_close > latest_ema200:
        trend_score += 25.0
        reasons.append("Price above EMA200")
    if latest_ema20 > latest_ema50 > latest_ema200:
        trend_score += 25.0
        reasons.append("EMA stack bullish")

    metrics = {
        "price": round(latest_close, 2),
        "ema20": round(latest_ema20, 2),
        "ema50": round(latest_ema50, 2),
        "ema200": round(latest_ema200, 2),
    }
    return round(min(trend_score, 100.0), 2), metrics, reasons


def score_market_momentum(index_df: pd.DataFrame, config: ScannerConfig) -> Tuple[float, Dict[str, float], List[str]]:
    """Score 20/50/100-day market momentum on a 0-100 scale."""
    if index_df is None or index_df.empty or len(index_df) < 110:
        return 0.0, {"reason": "insufficient_data"}, []

    close = pd.to_numeric(index_df["Close"], errors="coerce").dropna()
    if close.empty or len(close) < 110:
        return 0.0, {"reason": "missing_close"}, []

    cap = max(float(config.market_regime_momentum_return_cap_pct), 1.0)
    r20 = pct_change(close, 20)
    r50 = pct_change(close, 50)
    r100 = pct_change(close, 100)

    def _normalize(ret: float) -> float:
        if pd.isna(ret):
            return 0.0
        return max(min((ret / cap) * 100.0, 100.0), -100.0)

    normalized = [max(_normalize(r20), 0.0), max(_normalize(r50), 0.0), max(_normalize(r100), 0.0)]
    score = sum(normalized) / len(normalized)
    reasons: List[str] = []
    if r20 > 0:
        reasons.append("20D return positive")
    if r50 > 0:
        reasons.append("50D return positive")
    if r100 > 0:
        reasons.append("100D return positive")

    metrics = {
        "return_20d_pct": round(float(r20), 2),
        "return_50d_pct": round(float(r50), 2),
        "return_100d_pct": round(float(r100), 2),
    }
    return round(min(max(score, 0.0), 100.0), 2), metrics, reasons


def classify_market_regime(score: float, config: ScannerConfig) -> Tuple[str, float, float]:
    """Classify the regime and return a score multiplier plus BUY floor."""
    if score >= config.market_regime_bullish_threshold:
        return "BULLISH", config.market_regime_bullish_penalty, config.market_regime_buy_min_bullish
    if score >= config.market_regime_neutral_threshold:
        return "NEUTRAL", config.market_regime_neutral_penalty, config.market_regime_buy_min_neutral
    if score >= config.market_regime_caution_threshold:
        return "CAUTION", config.market_regime_caution_penalty, config.market_regime_buy_min_caution
    return "BEARISH", config.market_regime_bearish_penalty, config.market_regime_buy_min_bearish


def aggregate_market_regime(
    trend_score: float,
    breadth_score: float,
    momentum_score: float,
    volume_score: float,
    volatility_score: float,
    config: ScannerConfig,
) -> float:
    """Aggregate weighted market regime score."""
    weighted = (
        trend_score * config.market_regime_trend_weight
        + breadth_score * config.market_regime_breadth_weight
        + momentum_score * config.market_regime_momentum_weight
        + volume_score * config.market_regime_volume_weight
        + volatility_score * config.market_regime_volatility_weight
    )
    return round(min(max(weighted, 0.0), 100.0), 2)
