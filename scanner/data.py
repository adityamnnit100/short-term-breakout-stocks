"""Data-loading helpers for the scanner package."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional
import concurrent.futures
import os
import time

import pandas as pd
from market_data import load_symbol_universe

from utils.threading import _YFINANCE_LOCK
from .config import ScannerConfig
from utils.yf_cache import cached_download, load_disk_cached_history
from utils.cache import load_normalized_cache, save_normalized_cache

logger = logging.getLogger("AlphaScanner.Data")


def _load_valid_disk_history(ticker: str, config: ScannerConfig) -> pd.DataFrame:
    cached = normalize_columns(load_disk_cached_history(ticker, config.interval))
    if not cached.empty and all(col in cached.columns for col in config.required_columns):
        return cached.dropna(subset=config.required_columns).copy()
    return pd.DataFrame()


def _download_history_chunk(chunk: list, config: ScannerConfig, use_cache: bool, lock_download: bool) -> tuple[list, pd.DataFrame]:
    # Add retry logic to improve robustness for transient network errors.
    attempts = 3
    delay = 1.0
    df_batch = pd.DataFrame()
    for attempt in range(1, attempts + 1):
        try:
            if lock_download:
                with _YFINANCE_LOCK:
                    df_batch = cached_download(
                        chunk,
                        period=config.lookback_period,
                        interval=config.interval,
                        use_cache=use_cache,
                        progress=False,
                        auto_adjust=False,
                        threads=False,
                    )
            else:
                df_batch = cached_download(
                    chunk,
                    period=config.lookback_period,
                    interval=config.interval,
                    use_cache=use_cache,
                    progress=False,
                    auto_adjust=False,
                    threads=False,
                )
            # success
            break
        except Exception as exc:
            logger.warning(
                "Batch download attempt %d/%d failed for chunk size=%d: %s",
                attempt,
                attempts,
                len(chunk),
                exc,
            )
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
            else:
                logger.error("Critical error during batch download chunk size=%d: %s", len(chunk), exc)
                df_batch = pd.DataFrame()

    if df_batch is None or df_batch.empty:
        return chunk, pd.DataFrame()

    return chunk, df_batch


def _effective_chunk_size(config: ScannerConfig, use_cache: bool, universe_size: int) -> int:
    configured = max(1, int(getattr(config, "scan_download_chunk_size", 25) or 25))
    if use_cache:
        return configured
    # Fresh scans benefit from smaller live-download batches so we can spread the
    # network work across more workers without changing the data itself.
    if universe_size >= 400:
        return max(5, min(configured, 8))
    if universe_size >= 200:
        return max(5, min(configured, 10))
    if universe_size >= 100:
        return max(5, min(configured, 12))
    if universe_size >= 50:
        return max(5, min(configured, 15))
    return configured
    
    # Ensure the chunk size is not excessively large relative to CPU capacity.
    # Cap at cpu_count * 4 to avoid overloading the downloader with huge batches.
    try:
        cpu = os.cpu_count() or 1
        return min(configured, max(1, cpu * 4))
    except Exception:
        return configured

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
    # Prefer normalized cache if enabled (avoids re-normalizing and recomputing indicators)
    if use_cache and getattr(config, "persist_normalized", False):
        cached_norm = load_normalized_cache(ticker, config.interval, getattr(config, "cache_dir", "data/cache/normalized"), getattr(config, "cache_ttl_days", 7))
        if isinstance(cached_norm, pd.DataFrame) and not cached_norm.empty and all(col in cached_norm.columns for col in config.required_columns):
            logger.debug("download_history normalized cache hit for %s rows=%s", ticker, len(cached_norm))
            return cached_norm

    if use_cache:
        cached = _load_valid_disk_history(ticker, config)
        if not cached.empty:
            logger.debug("download_history disk cache hit for %s rows=%s", ticker, len(cached))
            return cached

    with _YFINANCE_LOCK:
        try:
            df = cached_download(
                ticker,
                period=config.lookback_period,
                interval=config.interval,
                use_cache=use_cache,
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception as exc:  # pragma: no cover - network/path dependent
            logger.warning("Failed to download %s: %s", ticker, exc)
            return pd.DataFrame()

    if isinstance(df, pd.DataFrame):
        df = normalize_columns(df)
        if not df.empty and all(col in df.columns for col in config.required_columns):
            df_clean = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
            logger.debug("download_history success for %s rows=%s cols=%s", ticker, len(df_clean), list(df_clean.columns))
            # Save normalized cache for future runs if enabled
            try:
                if getattr(config, "persist_normalized", False):
                    save_normalized_cache(df_clean, ticker, config.interval, getattr(config, "cache_dir", "data/cache/normalized"), config)
            except Exception:
                logger.debug("Failed to save normalized cache for %s", ticker)
            return df_clean

    logger.debug("download_history returned empty/invalid frame for %s", ticker)
    return pd.DataFrame()


def download_history_batch(tickers: Iterable[str], config: ScannerConfig, use_cache: bool = True) -> Dict[str, pd.DataFrame]:
    """Download a batch of ticker histories, preferably in a single bulk request for efficiency and stability."""
    tickers_list = sorted([ticker for ticker in tickers if isinstance(ticker, str) and ticker])
    if not tickers_list:
        return {}

    logger.debug(
        "download_history_batch(size=%d, period=%s, interval=%s, use_cache=%s, head=%s)",
        len(tickers_list),
        config.lookback_period,
        config.interval,
        use_cache,
        tickers_list[:5],
    )

    result: Dict[str, pd.DataFrame] = {}
    chunk_size = _effective_chunk_size(config, use_cache, len(tickers_list))
    chunks = [tickers_list[i:i + chunk_size] for i in range(0, len(tickers_list), chunk_size)]

    missing_tickers = tickers_list
    if use_cache:
        missing_tickers = []
        for ticker in tickers_list:
            cached = _load_valid_disk_history(ticker, config)
            if not cached.empty:
                result[ticker] = cached
            else:
                missing_tickers.append(ticker)

        if not missing_tickers:
            logger.info(
                "download_history_batch satisfied entirely from disk cache for %d tickers.",
                len(result),
            )
            return result

        logger.info(
            "download_history_batch disk cache hit for %d/%d tickers; fetching %d missing symbols.",
            len(result),
            len(tickers_list),
            len(missing_tickers),
        )

    chunks = [missing_tickers[i:i + chunk_size] for i in range(0, len(missing_tickers), chunk_size)]

    parallel_downloads = (not use_cache) and len(chunks) > 1 and int(getattr(config, "scan_download_threads", 1) or 1) > 1
    if parallel_downloads:
        # Cap workers by configured threads, number of chunks, and a CPU-aware limit
        configured_threads = max(1, int(getattr(config, "scan_download_threads", 1) or 1))
        cpu_limit = max(1, (os.cpu_count() or 1) * 2)
        max_workers = min(configured_threads, len(chunks), cpu_limit)
        logger.info(
            "download_history_batch fetching %d live chunks with %d workers (chunk_size=%d).",
            len(chunks),
            max_workers,
            chunk_size,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_download_history_chunk, chunk, config, use_cache, False) for chunk in chunks]
            for future in concurrent.futures.as_completed(futures):
                chunk, df_batch = future.result()
                if df_batch is None or df_batch.empty:
                    logger.debug("Batch download chunk returned no data for %d tickers.", len(chunk))
                    continue
                for ticker in chunk:
                    try:
                        if isinstance(df_batch.columns, pd.MultiIndex):
                            df_ticker = df_batch.xs(ticker, axis=1, level=1)
                        else:
                            df_ticker = df_batch.copy()
                        df_normalized = normalize_columns(df_ticker)
                        if not df_normalized.empty and all(col in df_normalized.columns for col in config.required_columns):
                            df_clean = df_normalized.dropna(subset=config.required_columns).copy()
                            result[ticker] = df_clean
                            try:
                                if getattr(config, "persist_normalized", False):
                                    save_normalized_cache(df_clean, ticker, config.interval, getattr(config, "cache_dir", "data/cache/normalized"), config)
                            except Exception:
                                logger.debug("Failed to save normalized cache for %s from batch", ticker)
                    except KeyError:
                        logger.debug("No data for ticker %s in batch result.", ticker)
                    except Exception as exc:
                        logger.warning("Failed to process ticker %s from batch: %s", ticker, exc)
    else:
        for chunk in chunks:
            _, df_batch = _download_history_chunk(chunk, config, use_cache, lock_download=True)
            if df_batch is None or df_batch.empty:
                logger.debug("Batch download chunk returned no data for %d tickers.", len(chunk))
                df_batch = pd.DataFrame()

            for ticker in chunk:
                try:
                    if isinstance(df_batch.columns, pd.MultiIndex):
                        df_ticker = df_batch.xs(ticker, axis=1, level=1)
                    else:
                        df_ticker = df_batch.copy()
                    df_normalized = normalize_columns(df_ticker)
                    if not df_normalized.empty and all(col in df_normalized.columns for col in config.required_columns):
                        df_clean = df_normalized.dropna(subset=config.required_columns).copy()
                        result[ticker] = df_clean
                        try:
                            if getattr(config, "persist_normalized", False):
                                save_normalized_cache(df_clean, ticker, config.interval, getattr(config, "cache_dir", "data/cache/normalized"), config)
                        except Exception:
                            logger.debug("Failed to save normalized cache for %s from batch", ticker)
                        continue
                    if use_cache:
                        cached = _load_valid_disk_history(ticker, config)
                        if not cached.empty:
                            logger.warning("Using disk-cached batch history for %s after live download returned no data.", ticker)
                            result[ticker] = cached
                except KeyError:
                    if use_cache:
                        cached = _load_valid_disk_history(ticker, config)
                        if not cached.empty:
                            logger.warning("Using disk-cached batch history for %s after batch lookup failed.", ticker)
                            result[ticker] = cached
                        else:
                            logger.debug("No data for ticker %s in batch result.", ticker)
                    else:
                        logger.debug("No data for ticker %s in batch result.", ticker)
                except Exception as exc:
                    logger.warning("Failed to process ticker %s from batch: %s", ticker, exc)

    logger.debug("download_history_batch result count=%d", len(result))
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
        symbols = load_symbol_universe(getattr(config, "universe", "Nifty 500"))

        logger.debug("get_universe(%s) -> %s symbols", getattr(config, "universe", None), len(symbols) if symbols else 0)

        return [symbol for symbol in symbols if isinstance(symbol, str) and symbol.endswith(".NS")]
    except Exception as exc:
        logger.warning("Unable to resolve universe: %s", exc)
        return []
