"""Breadth scoring for market regime analysis."""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

import pandas as pd

from scanner.config import ScannerConfig
from scanner.indicators import ema
from utils.yf_cache import incremental_cached_download


def _normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    cleaned = df.copy()
    if isinstance(cleaned.columns, pd.MultiIndex):
        cleaned.columns = cleaned.columns.get_level_values(0)
    return cleaned


def _fetch_in_chunks(tickers: Iterable[str], config: ScannerConfig, interval: str = "1d", use_cache: bool = True) -> pd.DataFrame:
    tickers_list = [ticker for ticker in tickers if isinstance(ticker, str) and ticker]
    if not tickers_list:
        return pd.DataFrame()

    frames = []
    for start in range(0, len(tickers_list), 25):
        chunk = tickers_list[start:start + 25]
        try:
            df = incremental_cached_download(chunk, period=config.market_regime_nifty500_period, interval=interval, use_cache=use_cache)
        except Exception:
            continue
        if isinstance(df, pd.DataFrame) and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    try:
        return pd.concat(frames, axis=1, sort=True)
    except Exception:
        return pd.DataFrame()


def calculate_breadth_metrics(
    universe: Iterable[str],
    config: ScannerConfig,
    use_cache: bool = True,
) -> Tuple[float, Dict[str, float], Dict[str, float]]:
    """Return a breadth score, component metrics, and raw percentages."""
    df = _fetch_in_chunks(universe, config, interval="1d", use_cache=use_cache)
    if df is None or df.empty:
        return 0.0, {"reason": "breadth_data_unavailable"}, {}

    df = _normalize_history(df)
    if not isinstance(df.columns, pd.MultiIndex):
        return 0.0, {"reason": "breadth_multiindex_missing"}, {}

    try:
        close = df["Close"]
    except Exception:
        return 0.0, {"reason": "breadth_close_missing"}, {}

    if close.empty or len(close) < config.ema_slow:
        return 0.0, {"reason": "breadth_insufficient_history"}, {}

    latest = close.iloc[-1]
    ema20 = ema(close, config.ema_fast)
    ema50 = ema(close, config.ema_medium)
    ema200 = ema(close, config.ema_slow)

    above20 = (latest > ema20.iloc[-1]).mean() * 100.0
    above50 = (latest > ema50.iloc[-1]).mean() * 100.0
    above200 = (latest > ema200.iloc[-1]).mean() * 100.0

    score = 0.0
    score += min(max(above20 / 100.0, 0.0), 1.0) * 35.0
    score += min(max(above50 / 100.0, 0.0), 1.0) * 30.0
    score += min(max(above200 / 100.0, 0.0), 1.0) * 35.0

    raw = {
        "pct_above_ema20": round(float(above20), 2),
        "pct_above_ema50": round(float(above50), 2),
        "pct_above_ema200": round(float(above200), 2),
    }
    metrics = {
        **raw,
        "breadth_alignment": round(float((above20 + above50 + above200) / 3.0), 2),
    }
    return round(min(score, 100.0), 2), metrics, raw
