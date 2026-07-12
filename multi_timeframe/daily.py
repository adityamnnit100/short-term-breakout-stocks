"""Daily confirmation scoring based on existing scanner output."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from scanner.config import ScannerConfig


def _find_score_value(row: pd.Series) -> Tuple[float, str]:
    candidates = ["Entry Score", "Watchlist Score", "Total Score", "Signal_Strength", "score"]
    for column in candidates:
        if column in row and pd.notna(row.get(column)):
            try:
                return float(row.get(column)), column
            except Exception:
                continue
    return 0.0, ""


def score_daily_confirmation(row: pd.Series, config: ScannerConfig) -> Tuple[float, Dict[str, float], List[str]]:
    """Translate the scanner's existing score into a 0-50 daily confirmation score."""
    base_score, source = _find_score_value(row)
    if source == "Signal_Strength":
        score = max(min(base_score, 10.0), 0.0) * 5.0
    elif base_score > 50.0:
        score = max(min(base_score, 100.0), 0.0) * 0.5
    else:
        score = max(min(base_score, 50.0), 0.0)

    reasons: List[str] = []
    if source:
        reasons.append(f"Daily scanner score sourced from {source}")
    if score >= config.mtf_daily_bullish_threshold:
        reasons.append("Daily bullish confirmation")
    elif score >= config.mtf_daily_neutral_threshold:
        reasons.append("Daily constructive")
    else:
        reasons.append("Daily weak")

    metrics = {
        "daily_source_score": round(float(base_score), 2),
        "daily_source_name": source,
    }
    return round(min(max(score, 0.0), 50.0), 2), metrics, reasons
