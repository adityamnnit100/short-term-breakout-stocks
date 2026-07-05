"""Sector rotation and relative strength helpers."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd

from .config import ScannerConfig
from .indicators import pct_change


def infer_sector(df: pd.DataFrame, sector_map: Optional[Dict[str, str]] = None, ticker: Optional[str] = None) -> str:
    if sector_map and ticker:
        return str(sector_map.get(ticker, "Unknown"))
    return "Unknown"


def calculate_sector_score(df: pd.DataFrame, benchmark: pd.Series, config: ScannerConfig, sector_map: Optional[Dict[str, str]] = None, ticker: Optional[str] = None) -> Tuple[float, dict]:
    """Score sector strength using simple relative-return logic."""
    if df is None or df.empty or len(df) < config.min_candles:
        return 0.0, {"reason": "insufficient_data"}

    sector = infer_sector(df, sector_map, ticker)
    if sector in config.sector_blacklist:
        return 0.0, {"reason": "blacklisted_sector", "sector": sector}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty or benchmark.empty:
        return 0.0, {"reason": "missing_benchmark"}

    stock_return = pct_change(close, 60)
    benchmark_return = pct_change(benchmark.dropna(), 60)
    relative_return = stock_return - benchmark_return if not pd.isna(benchmark_return) else stock_return

    score = 0.0
    if relative_return > 0:
        score += 70.0
    if stock_return > 10:
        score += 30.0

    metrics = {"sector": sector, "stock_return_60d": round(stock_return, 2), "benchmark_return_60d": round(benchmark_return, 2)}
    return round(min(score, 100.0), 2), metrics
