"""Simple in-memory cache wrapper around yfinance.download to avoid
re-downloading the same tickers repeatedly during a single app/session run.

This cache is intentionally lightweight: process-local, thread-safe and
intended for short-term reuse within a scanner/backtest run.
"""
from typing import Union, Iterable, Tuple
import threading
import time
import hashlib
import pickle
from pathlib import Path
import pandas as pd
import datetime

_CACHE = {}
_LOCK = threading.Lock()


def _normalize_interval(interval: str) -> str:
    """Map UI-friendly interval labels to yfinance-compatible values."""
    value = str(interval or "1d").strip().lower()
    aliases = {
        "daily": "1d",
        "day": "1d",
        "1day": "1d",
        "1d": "1d",
        "1wk": "1wk",
        "weekly": "1wk",
        "week": "1wk",
        "1w": "1wk",
        "1mo": "1mo",
        "monthly": "1mo",
        "month": "1mo",
        "1m": "1mo",
        "60m": "60m",
        "1h": "1h",
        "1hour": "1h",
        "60min": "60m",
        "30m": "30m",
        "15m": "15m",
        "5m": "5m",
        "5min": "5m",
    }
    return aliases.get(value, value if value in {"1d", "1wk", "1mo", "60m", "30m", "15m", "5m", "1h", "4h", "90m", "2m", "1m"} else "1d")


def _make_key(tickers: Union[str, Iterable[str]], period: str, interval: str, opts: dict) -> bytes:
    if isinstance(tickers, str):
        tick_key = tickers
    else:
        # Preserve order because callers may rely on ordering for chunking
        tick_key = ",".join(tickers)
    meta = (tick_key, period, interval, tuple(sorted(opts.items())))
    return hashlib.sha1(pickle.dumps(meta)).digest()


def cached_download(tickers: Union[str, Iterable[str]], period: str = "1y", interval: str = "1d", use_cache: bool = True, **yf_kwargs):
    """Download via yfinance but keep a short-lived in-memory cache keyed by the
    (tickers, period, interval, other-kwargs). Returns the same pandas.DataFrame
    that `yfinance.download` returns.

    Set `use_cache=False` to force a fresh network fetch for UI-driven scans.
    """
    try:
        import yfinance as yf
    except Exception:
        # If yfinance isn't available, raise early so callers can handle it
        raise

    interval = _normalize_interval(interval)

    if use_cache:
        key = _make_key(tickers, period, interval, {k: yf_kwargs.get(k) for k in yf_kwargs})

        with _LOCK:
            if key in _CACHE:
                return _CACHE[key]

    # Not cached; fetch and store
    df = yf.download(tickers, period=period, interval=interval, **yf_kwargs)

    if use_cache:
        with _LOCK:
            _CACHE[key] = df

    return df


def _cache_path_for_ticker(ticker: str, interval: str) -> Path:
    safe = ticker.replace('/', '_').replace('.', '_')
    p = Path('data/cache')
    p.mkdir(parents=True, exist_ok=True)
    return p / f"yf_{safe}_{interval}.pkl"


def _period_to_days(period: str) -> int:
    s = str(period).lower()
    if s.endswith('y'):
        return int(float(s[:-1]) * 365)
    if s.endswith('mo'):
        return int(float(s[:-2]) * 30)
    if s.endswith('d'):
        return int(float(s[:-1]))
    # default 365 days
    try:
        return int(s)
    except Exception:
        return 365


def incremental_cached_download(tickers: Iterable[str], period: str = '1y', interval: str = '1d', start_date: str = None, use_cache: bool = True, **yf_kwargs):
    """For each ticker, use a per-ticker disk cache and only fetch missing candles.
    Returns a concatenated DataFrame similar to `yfinance.download` for multiple tickers.

    Set `use_cache=False` to bypass the disk cache and force a fresh fetch.
    """
    try:
        import yfinance as yf
    except Exception:
        raise
    interval = _normalize_interval(interval)
    results = []
    days = _period_to_days(period)
    start_needed = (pd.Timestamp.now().normalize() - pd.Timedelta(days=days))

    tickers_list = list(tickers)
    if len(tickers_list) > 10:
        chunked_results = []
        for start in range(0, len(tickers_list), 10):
            subchunk = tickers_list[start:start + 10]
            sub_df = incremental_cached_download(
                subchunk,
                period=period,
                interval=interval,
                start_date=start_date,
                use_cache=use_cache,
                **yf_kwargs,
            )
            if isinstance(sub_df, pd.DataFrame) and not sub_df.empty:
                chunked_results.append(sub_df)

        if not chunked_results:
            return pd.DataFrame()

        try:
            return pd.concat(chunked_results, axis=1, sort=True)
        except Exception:
            return pd.DataFrame()

    if not use_cache:
        try:
            bulk = yf.download(tickers_list, period=period, interval=interval, progress=False, auto_adjust=False, threads=True, **yf_kwargs)
        except Exception:
            bulk = pd.DataFrame()

        if isinstance(bulk, pd.DataFrame) and not bulk.empty:
            return bulk

        results = []
        for ticker in tickers_list:
            try:
                combined = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False, **yf_kwargs)
                if isinstance(combined.columns, pd.MultiIndex):
                    combined.columns = combined.columns.get_level_values(0)
                if combined is not None and not combined.empty:
                    df2 = combined.copy()
                    df2.columns = pd.MultiIndex.from_product([df2.columns, [ticker]]) if not isinstance(df2.columns, pd.MultiIndex) else df2.columns
                    results.append(df2)
            except Exception:
                continue

        if not results:
            return pd.DataFrame()

        try:
            return pd.concat(results, axis=1, sort=True)
        except Exception:
            return pd.DataFrame()

    # First attempt a bulk chunk download (fewer network roundtrips, less rate-limiting)
    try:
        # yfinance's internal threading (`threads=True`) is a known source of instability and
        # segmentation faults in complex applications. It must be disabled globally.
        # The `threads=False` argument here ensures stability, overriding any value
        # that might be passed in yf_kwargs.
        yf_kwargs['threads'] = False
        bulk = yf.download(tickers_list, period=period, interval=interval, progress=False, auto_adjust=False, **yf_kwargs)
    except Exception:
        bulk = pd.DataFrame()

    if isinstance(bulk, pd.DataFrame) and not bulk.empty:
        # Split bulk into per-ticker frames and persist
        for ticker in tickers_list:
            try:
                if isinstance(bulk.columns, pd.MultiIndex):
                    df_t = bulk.xs(ticker, axis=1, level=1).copy()
                else:
                    # bulk may be single-ticker DataFrame
                    df_t = bulk.copy()
                if isinstance(df_t.columns, pd.MultiIndex):
                    df_t.columns = df_t.columns.get_level_values(0)
                path = _cache_path_for_ticker(ticker, interval)
                df_t.to_pickle(path)
                # prepare for concatenation
                df2 = df_t.copy()
                df2.columns = pd.MultiIndex.from_product([df2.columns, [ticker]])
                results.append(df2)
            except Exception:
                continue
    else:
        # Fallback to per-ticker update (delta fetch)
        for ticker in tickers_list:
            path = _cache_path_for_ticker(ticker, interval)
            cached = None
            if path.exists():
                try:
                    cached = pd.read_pickle(path)
                except Exception:
                    cached = None

            # If cached covers the requested start, slice and use
            combined = None
            if cached is not None and not cached.empty:
                cached_index = cached.index.max()
                if cached.index.min() <= start_needed:
                    # Cached covers full requested range; ensure upto date
                    if cached_index >= pd.Timestamp.now().normalize():
                        combined = cached.loc[cached.index >= start_needed]
                    else:
                        # Need to fetch tail only
                        fetch_start = cached_index + pd.Timedelta(days=1)
                        try:
                            tail = yf.download(ticker, start=fetch_start.strftime('%Y-%m-%d'), interval=interval, progress=False, auto_adjust=False, **yf_kwargs)
                            if isinstance(tail.columns, pd.MultiIndex):
                                tail.columns = tail.columns.get_level_values(0)
                            if tail is not None and not tail.empty:
                                combined = pd.concat([cached, tail]).drop_duplicates().sort_index()
                            else:
                                combined = cached
                        except Exception:
                            combined = cached
                else:
                    # Cached does not go back enough; fetch full period
                    try:
                        combined = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False, **yf_kwargs)
                        if isinstance(combined.columns, pd.MultiIndex):
                            combined.columns = combined.columns.get_level_values(0)
                    except Exception:
                        combined = cached
            else:
                # No cache available; fetch full period
                try:
                    combined = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False, **yf_kwargs)
                    if isinstance(combined.columns, pd.MultiIndex):
                        combined.columns = combined.columns.get_level_values(0)
                except Exception:
                    combined = pd.DataFrame()

            # Save combined back to cache and append
            try:
                if combined is not None and not combined.empty:
                    combined.to_pickle(path)
                    df2 = combined.copy()
                    df2.columns = pd.MultiIndex.from_product([df2.columns, [ticker]]) if not isinstance(df2.columns, pd.MultiIndex) else df2.columns
                    results.append(df2)
            except Exception:
                pass

    if not results:
        return pd.DataFrame()

    try:
        out = pd.concat(results, axis=1, sort=True)
        return out
    except Exception:
        return pd.DataFrame()


def _last_run_path(timeframe: str) -> Path:
    p = Path('data/cache')
    p.mkdir(parents=True, exist_ok=True)
    return p / f"last_scan_{timeframe}.txt"


def set_last_scan_time(timeframe: str, when: pd.Timestamp = None):
    path = _last_run_path(timeframe)
    when = when or pd.Timestamp.now()
    try:
        path.write_text(when.isoformat())
    except Exception:
        pass


def get_last_scan_time(timeframe: str) -> pd.Timestamp:
    path = _last_run_path(timeframe)
    if not path.exists():
        return None
    try:
        txt = path.read_text()
        return pd.to_datetime(txt)
    except Exception:
        return None


def clear_cache():
    with _LOCK:
        _CACHE.clear()


def cache_size() -> int:
    with _LOCK:
        return len(_CACHE)
