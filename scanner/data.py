"""Data-loading helpers for the scanner package."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

import pandas as pd
from breakout import get_nifty_500, get_nifty_total_market

from .config import ScannerConfig
from utils.yf_cache import cached_download

logger = logging.getLogger(__name__)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column casing and preserve the OHLCV schema expected by the scanner."""
    if df is None or df.empty:
        return df

    cleaned = df.copy()
    if isinstance(cleaned.columns, pd.MultiIndex):
        cleaned.columns = cleaned.columns.get_level_values(0)

    renamed = {}
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        matches = [c for c in cleaned.columns if str(c).lower() == str(column).lower()]
        if matches:
            renamed[matches[0]] = column
    cleaned.rename(columns=renamed, inplace=True)
    return cleaned


def download_history(ticker: str, config: ScannerConfig) -> pd.DataFrame:
    """Download daily history for a ticker with basic validation."""
    try:
        df = cached_download(ticker, period=config.lookback_period, interval=config.interval, progress=False, auto_adjust=False, threads=False)
    except Exception as exc:  # pragma: no cover - network/path dependent
        logger.warning("Failed to download %s: %s", ticker, exc)
        return pd.DataFrame()

    if isinstance(df, pd.DataFrame):
        df = normalize_columns(df)
        if not df.empty and all(col in df.columns for col in config.required_columns):
            return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
    return pd.DataFrame()


def download_history_batch(tickers: Iterable[str], config: ScannerConfig) -> Dict[str, pd.DataFrame]:
    """Download a batch of ticker histories in one request and split them per symbol."""
    tickers_list = [ticker for ticker in tickers if isinstance(ticker, str) and ticker]
    if not tickers_list:
        return {}

    try:
        df = cached_download(
            tickers_list,
            period=config.lookback_period,
            interval=config.interval,
            progress=False,
            auto_adjust=False,
            threads=True,
        )
    except Exception as exc:  # pragma: no cover - network/path dependent
        logger.warning("Batch download failed: %s", exc)
        return {}

    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}

    result: Dict[str, pd.DataFrame] = {}
    if isinstance(df.columns, pd.MultiIndex):
        level0 = [str(value) for value in df.columns.get_level_values(0)]
        level1 = [str(value) for value in df.columns.get_level_values(1)]
        for ticker in tickers_list:
            try:
                if ticker in level1:
                    sub_df = df.xs(ticker, axis=1, level=1).copy()
                elif ticker in level0:
                    sub_df = df.xs(ticker, axis=1, level=0).copy()
                else:
                    continue
                sub_df = normalize_columns(sub_df)
                if not sub_df.empty and all(col in sub_df.columns for col in config.required_columns):
                    result[ticker] = sub_df.dropna(subset=config.required_columns).copy()
            except Exception:
                continue
        return result

    # Single-ticker style frame. Return it for the first requested symbol.
    normalized = normalize_columns(df)
    if not normalized.empty and all(col in normalized.columns for col in config.required_columns):
        result[tickers_list[0]] = normalized.dropna(subset=config.required_columns).copy()
    return result


def download_benchmark(config: ScannerConfig) -> pd.Series:
    """Download benchmark index close prices for relative strength comparisons."""
    try:
        import yfinance as yf

        benchmark = yf.download("^NSEI", period=config.lookback_period, interval=config.interval, progress=False, auto_adjust=False, threads=False)
    except Exception as exc:  # pragma: no cover - network/path dependent
        logger.warning("Benchmark download failed: %s", exc)
        return pd.Series(dtype=float)

    if isinstance(benchmark, pd.DataFrame):
        benchmark = normalize_columns(benchmark)
        if "Close" in benchmark.columns:
            return benchmark["Close"].dropna()
    return pd.Series(dtype=float)


def get_universe(config: ScannerConfig) -> List[str]:
    """Return the initial universe based on the selected scanner universe."""
    try:
        if getattr(config, "universe", "Nifty 500") == "Total Market (Cap Focused)":
            symbols = get_nifty_total_market()
        else:
            symbols = get_nifty_500()

        return [symbol for symbol in symbols if isinstance(symbol, str) and symbol.endswith(".NS")]
    except Exception as exc:
        logger.warning("Unable to resolve universe: %s", exc)
        return []
