"""Reporting helpers for the scanner package."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def save_results(results: pd.DataFrame, output_path: Optional[str] = None, columns: Optional[List[str]] = None) -> Optional[Path]:
    """Persist ranked scanner output to CSV and optionally to JSON."""
    if results is None or results.empty:
        return None
    path = Path(output_path or "data/scanner_results.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(path, index=False, columns=columns)
    logger.info("Saved %s rows to %s", len(results), path)
    return path


def format_results(results: pd.DataFrame) -> str:
    """Return a short text summary for console output."""
    if results is None or results.empty:
        return "No candidates met the configured thresholds."

    if "Watchlist Score" in results.columns:
        score_col = "Watchlist Score"
        detail_cols = ["Trend", "Base Score", "Volume Score", "Relative Strength"]
        entry_col = None
    elif "Entry Score" in results.columns:
        score_col = "Entry Score"
        detail_cols = ["Entry Price", "Stop Loss", "Risk Reward", "Breakout Volume Ratio"]
        entry_col = "Entry Price"
    elif "Total Score" in results.columns:
        score_col = "Total Score"
        detail_cols = ["Entry Zone", "Stop Loss"]
        entry_col = "Entry Zone"
    else:
        score_candidates = [column for column in results.columns if "score" in column.lower()]
        score_col = score_candidates[0] if score_candidates else results.columns[0]
        detail_cols = []
        entry_col = None

    lines = []
    for _, row in results.head(10).iterrows():
        ticker = row.get("Ticker", "N/A")
        score = row.get(score_col, "N/A")
        entry = row.get(entry_col, "-") if entry_col else "-"
        stop_loss = row.get("Stop Loss", row.get("Stop_Loss", "-"))
        extras = [f"{label}={row.get(label, '-')}" for label in detail_cols if label in results.columns]
        suffix = f" | {', '.join(extras)}" if extras else ""
        lines.append(f"{ticker} | score={score} | entry={entry} | sl={stop_loss}{suffix}")

    return "\n".join(lines)
