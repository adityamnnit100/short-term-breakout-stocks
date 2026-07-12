"""Multi-timeframe candidate ranking."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import pandas as pd

from scanner.config import ScannerConfig
from .daily import score_daily_confirmation
from .hourly import score_hourly_entry_timing
from .weekly import score_weekly_confirmation


def _weekly_state(score: float, config: ScannerConfig) -> str:
    if score >= config.mtf_weekly_bullish_threshold:
        return "BULLISH"
    if score >= config.mtf_weekly_neutral_threshold:
        return "NEUTRAL"
    if score >= config.mtf_weekly_bearish_threshold:
        return "WEAK"
    return "BEARISH"


def _recommendation(
    weekly_state: str,
    daily_score: float,
    hourly_score: float,
    adjusted_score: float,
    regime: Dict[str, object],
    config: ScannerConfig,
) -> str:
    regime_name = str(regime.get("regime", "NEUTRAL")).upper()
    regime_buy_floor = float(regime.get("buy_min_score", config.mtf_buy_threshold))
    effective_buy_floor = max(config.mtf_buy_threshold, regime_buy_floor)
    effective_strong_floor = max(config.mtf_strong_buy_threshold, effective_buy_floor + 5.0)

    if regime_name == "BEARISH":
        return "Avoid"
    if config.mtf_weekly_veto_enabled and weekly_state == "BEARISH":
        return "Avoid"
    if weekly_state == "WEAK" and regime_name in {"CAUTION", "BEARISH"}:
        return "Avoid"

    if weekly_state == "BULLISH" and daily_score >= config.mtf_daily_bullish_threshold and hourly_score >= config.mtf_hourly_bullish_threshold and adjusted_score >= effective_strong_floor:
        return "Strong Buy"
    if weekly_state in {"BULLISH", "NEUTRAL"} and daily_score >= config.mtf_daily_bullish_threshold and hourly_score >= config.mtf_hourly_neutral_threshold and adjusted_score >= effective_buy_floor:
        return "Buy"
    if weekly_state in {"BULLISH", "NEUTRAL"} and daily_score >= config.mtf_daily_neutral_threshold and hourly_score >= config.mtf_hourly_neutral_threshold:
        return "Watch"
    if weekly_state == "WEAK":
        return "Wait"
    return "Wait"


def rank_multi_timeframe_candidates(
    results: pd.DataFrame,
    history_loader: Callable[..., pd.DataFrame],
    regime_result: Optional[Dict[str, object]] = None,
    config: Optional[ScannerConfig] = None,
    max_candidates: int = 8,
) -> pd.DataFrame:
    """Rank scanner results using weekly, daily, and hourly confirmation."""
    config = config or ScannerConfig()
    regime_result = regime_result or {
        "score": 0.0,
        "regime": "NEUTRAL",
        "score_multiplier": 0.95,
        "buy_min_score": config.mtf_buy_threshold,
        "reasons": [],
        "components": {},
        "metrics": {},
    }

    if results is None or results.empty or "Ticker" not in results.columns:
        return pd.DataFrame()

    ranked_rows: List[Dict[str, object]] = []
    for _, row in results.iterrows():
        ticker = str(row.get("Ticker", "")).strip()
        if not ticker:
            continue

        try:
            weekly_df = history_loader(ticker, period=config.mtf_weekly_lookback_period, interval="1wk")
        except Exception:
            weekly_df = pd.DataFrame()
        try:
            hourly_df = history_loader(ticker, period=config.mtf_hourly_lookback_period, interval="1h")
        except Exception:
            hourly_df = pd.DataFrame()

        weekly_score, weekly_metrics, weekly_reasons = score_weekly_confirmation(weekly_df, config)
        daily_score, daily_metrics, daily_reasons = score_daily_confirmation(row, config)
        hourly_score, hourly_metrics, hourly_reasons = score_hourly_entry_timing(hourly_df, config)

        raw_score = (
            (weekly_score / max(config.mtf_weekly_max_points, 1.0)) * config.mtf_weekly_weight
            + (daily_score / max(config.mtf_daily_max_points, 1.0)) * config.mtf_daily_weight
            + (hourly_score / max(config.mtf_hourly_max_points, 1.0)) * config.mtf_hourly_weight
        )
        multiplier = float(regime_result.get("score_multiplier", 1.0) or 1.0)
        adjusted_score = min(max(raw_score * multiplier, 0.0), 100.0)
        weekly_state = _weekly_state(weekly_score, config)
        recommendation = _recommendation(weekly_state, daily_score, hourly_score, adjusted_score, regime_result, config)

        reasons = []
        reasons.extend(weekly_reasons[:3])
        reasons.extend(daily_reasons[:2])
        reasons.extend(hourly_reasons[:3])
        reasons.extend([str(reason) for reason in regime_result.get("reasons", [])[:2]])

        weaknesses = []
        if weekly_state in {"WEAK", "BEARISH"}:
            weaknesses.append("Weekly trend not fully aligned")
        if hourly_score < config.mtf_hourly_neutral_threshold:
            weaknesses.append("Intraday timing is weak")
        if str(regime_result.get("regime", "NEUTRAL")).upper() != "BULLISH":
            weaknesses.append(f"Market regime is {regime_result.get('regime', 'NEUTRAL')}")

        ranked_rows.append(
            {
                "Ticker": ticker,
                "Sector": row.get("Sector", "Unknown"),
                "Weekly Score": round(float(weekly_score), 2),
                "Daily Score": round(float(daily_score), 2),
                "1H Score": round(float(hourly_score), 2),
                "Raw Score": round(float(raw_score), 2),
                "Final Score": round(float(adjusted_score), 2),
                "Weekly State": weekly_state,
                "Market Regime": regime_result.get("regime", "NEUTRAL"),
                "Market Regime Score": round(float(regime_result.get("score", 0.0) or 0.0), 2),
                "Market Multiplier": round(float(multiplier), 2),
                "Recommendation": recommendation,
                "Reasons": reasons,
                "Weaknesses": weaknesses,
                "Weekly Metrics": weekly_metrics,
                "Daily Metrics": daily_metrics,
                "Hourly Metrics": hourly_metrics,
            }
        )

    if not ranked_rows:
        return pd.DataFrame()

    ranked = pd.DataFrame(ranked_rows).sort_values("Final Score", ascending=False)
    return ranked.head(max_candidates).reset_index(drop=True)
