"""Data-loading helpers for the scanner package."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional
import concurrent.futures

import pandas as pd
from breakout import get_nifty_500, get_nifty_total_market

from utils.threading import _YFINANCE_LOCK
from .config import ScannerConfig
from utils.yf_cache import cached_download

logger = logging.getLogger("AlphaScanner.Data")

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column casing and preserve the OHLCV schema expected by the scanner."""
    if df is None or df.empty:
        return df

    cleaned = df.copy()
    # Flatten multi-index headers if they exist, which can happen with yfinance
    if isinstance(cleaned.columns, pd.MultiIndex):
        cleaned.columns = cleaned.columns.get_level_values(0)

    # Standardize all columns to lowercase to handle casing differences robustly
    # (e.g., 'open' vs 'Open').
    cleaned.columns = [str(c).lower() for c in cleaned.columns]

    # After lowercasing, duplicates might exist (e.g., 'adj close' and 'close'
    # from different sources). Remove duplicates, keeping the first occurrence,
    # which is typically the most reliable column.
    cleaned = cleaned.loc[:, ~cleaned.columns.duplicated(keep='first')]

    # Capitalize the essential columns to the expected 'TitleCase' format.
    rename_map = {
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    }
    cleaned.rename(columns=rename_map, inplace=True)
    return cleaned


def download_history(ticker: str, config: ScannerConfig, use_cache: bool = True) -> pd.DataFrame:
    """Download daily history for a ticker with basic validation."""
    logger.debug(
        "download_history(ticker=%s, period=%s, interval=%s, use_cache=%s)",
        ticker,
        config.lookback_period,
        config.interval,
        use_cache,
    )
    with _YFINANCE_LOCK:
        try:
            df = cached_download(ticker, period=config.lookback_period, interval=config.interval, use_cache=use_cache, progress=False, auto_adjust=False, threads=False)
        except Exception as exc:  # pragma: no cover - network/path dependent
            logger.warning("Failed to download %s: %s", ticker, exc)
            return pd.DataFrame()

    if isinstance(df, pd.DataFrame):
        df = normalize_columns(df)
        if not df.empty and all(col in df.columns for col in config.required_columns):
            logger.debug("download_history success for %s rows=%s cols=%s", ticker, len(df), list(df.columns))
            return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
    logger.debug("download_history returned empty/invalid frame for %s", ticker)
    return pd.DataFrame()


def download_history_batch(tickers: Iterable[str], config: ScannerConfig, use_cache: bool = True) -> Dict[str, pd.DataFrame]:
    """Download a batch of ticker histories in one request and split them per symbol."""
    tickers_list = [ticker for ticker in tickers if isinstance(ticker, str) and ticker]
    if not tickers_list:
        return {}

    logger.debug(
        "download_history_batch(size=%s, period=%s, interval=%s, use_cache=%s, head=%s)",
        len(tickers_list),
        config.lookback_period,
        config.interval,
        use_cache,
        tickers_list[:5],
    )
    
    result: Dict[str, pd.DataFrame] = {}
    # Use a controlled ThreadPoolExecutor to parallelize single-ticker downloads.
    # This is a more stable approach than relying on yfinance's internal threading.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        # We are calling `download_history` which is already configured for single tickers
        # and has threading disabled internally.
        future_to_ticker = {
            executor.submit(download_history, ticker, config, use_cache): ticker
            for ticker in tickers_list
        }
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    result[ticker] = df
            except Exception as exc:
                logger.warning(
                    "Failed to download %s during batch operation: %s", ticker, exc
                )

    logger.debug(
        "download_history_batch (ThreadPool) result count=%s", len(result)
    )
    return result


def download_benchmark(config: ScannerConfig) -> pd.Series:
    """Download benchmark index close prices for relative strength comparisons."""
    logger.debug("download_benchmark(period=%s, interval=%s)", config.lookback_period, config.interval)
    try:
        with _YFINANCE_LOCK:
            import yfinance as yf

            benchmark = yf.download("^NSEI", period=config.lookback_period, interval=config.interval, progress=False, auto_adjust=False, threads=False)
    except Exception as exc:  # pragma: no cover - network/path dependent
        logger.warning("Benchmark download failed: %s", exc)
        return pd.Series(dtype=float)

    if isinstance(benchmark, pd.DataFrame):
        benchmark = normalize_columns(benchmark)
        if "Close" in benchmark.columns:
            logger.debug("download_benchmark success rows=%s", len(benchmark))
            return benchmark["Close"].dropna()
    logger.debug("download_benchmark returned empty series")
    return pd.Series(dtype=float)


def get_universe(config: ScannerConfig) -> List[str]:
    """Return the initial universe based on the selected scanner universe."""
    try:
        if getattr(config, "universe", "Nifty 500") == "Total Market (Cap Focused)":
            symbols = get_nifty_total_market()
        else:
            symbols = get_nifty_500()

        logger.debug("get_universe(%s) -> %s symbols", getattr(config, "universe", None), len(symbols) if symbols else 0)

        return [symbol for symbol in symbols if isinstance(symbol, str) and symbol.endswith(".NS")]
    except Exception as exc:
        logger.warning("Unable to resolve universe: %s", exc)
        return []
