"""Simple file-backed cache helpers for normalized DataFrames and indicators.

Functions here provide atomic write/read helpers for parquet + metadata so the
scanner can persist normalized frames and avoid recomputing indicators on every
run.
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, Optional

import pandas as pd

CACHE_META_VERSION = "1"
# Bump this when cache schema or attached indicators change.
CACHE_SCHEMA_VERSION = "v1"


def _safe_name(ticker: str, interval: str) -> str:
    name = f"{ticker}_{interval}".replace("/", "_").replace(".", "_")
    return name


def _paths(cache_dir: str, ticker: str, interval: str) -> Dict[str, str]:
    safe = _safe_name(ticker, interval)
    parquet = os.path.join(cache_dir, f"normalized_{safe}.parquet")
    meta = os.path.join(cache_dir, f"normalized_{safe}.json")
    return {"parquet": parquet, "meta": meta}


def _ensure_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def load_normalized_cache(ticker: str, interval: str, cache_dir: str, ttl_days: int) -> pd.DataFrame:
    paths = _paths(cache_dir, ticker, interval)
    meta_path = paths["meta"]
    parquet_path = paths["parquet"]
    try:
        if not os.path.exists(parquet_path) or not os.path.exists(meta_path):
            return pd.DataFrame()
        with open(meta_path, "r") as fh:
            meta = json.load(fh)
        updated = float(meta.get("updated", 0))
        # Invalidate if schema/version mismatch
        if meta.get("schema", None) != CACHE_SCHEMA_VERSION:
            return pd.DataFrame()
        if ttl_days is not None and ttl_days > 0:
            if time.time() - updated > float(ttl_days) * 86400:
                return pd.DataFrame()
        # read parquet
        df = pd.read_parquet(parquet_path)
        return df
    except Exception:
        return pd.DataFrame()


def save_normalized_cache(df: pd.DataFrame, ticker: str, interval: str, cache_dir: str, config: Optional[object] = None) -> None:
    paths = _paths(cache_dir, ticker, interval)
    parquet_path = paths["parquet"]
    meta_path = paths["meta"]
    _ensure_dir(os.path.dirname(parquet_path))
    # atomic write: write to temp then replace
    try:
        # Optionally compute and attach standard indicators to the frame before persisting
        if config is not None:
            try:
                from scanner.indicators import ema, atr  # local import to avoid cycles

                # Add EMAs
                try:
                    fast = int(getattr(config, "ema_fast", 20))
                    med = int(getattr(config, "ema_medium", 50))
                    slow = int(getattr(config, "ema_slow", 200))
                    df[f"EMA_{fast}"] = ema(df["Close"], fast)
                    df[f"EMA_{med}"] = ema(df["Close"], med)
                    df[f"EMA_{slow}"] = ema(df["Close"], slow)
                except Exception:
                    pass

                # Add ATR
                try:
                    atr_w = int(getattr(config, "atr_window", 20))
                    df[f"ATR_{atr_w}"] = atr(df, atr_w)
                except Exception:
                    pass
                # Add VWAP and Relative Volume (RVol) for intraday analysis
                try:
                    from scanner.indicators import vwap, relative_volume

                    try:
                        df["VWAP"] = vwap(df)
                    except Exception:
                        pass

                    try:
                        rvol_window = int(getattr(config, "rvol_window", 20))
                        df[f"RVol_{rvol_window}"] = relative_volume(df, window=rvol_window)
                    except Exception:
                        # fallback to a default 20-window
                        try:
                            df["RVol_20"] = relative_volume(df, window=20)
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                pass

        tmp_parquet = parquet_path + ".tmp"
        df.to_parquet(tmp_parquet, index=True)
        os.replace(tmp_parquet, parquet_path)
        meta = {"version": CACHE_META_VERSION, "schema": CACHE_SCHEMA_VERSION, "rows": int(len(df)), "updated": time.time()}
        tmp_meta = meta_path + ".tmp"
        with open(tmp_meta, "w") as fh:
            json.dump(meta, fh)
        os.replace(tmp_meta, meta_path)
    except Exception:
        try:
            if os.path.exists(tmp_parquet):
                os.remove(tmp_parquet)
        except Exception:
            pass


def invalidate_normalized_cache(ticker: Optional[str] = None, interval: Optional[str] = None, cache_dir: str = "data/cache/normalized") -> int:
    """Invalidate (delete) cached normalized files.

    If `ticker` and `interval` are None, purge entire cache directory.
    Returns number of files removed.
    """
    removed = 0
    try:
        if ticker is None and interval is None:
            # remove all normalized_* files
            if not os.path.exists(cache_dir):
                return 0
            for name in os.listdir(cache_dir):
                if name.startswith("normalized_"):
                    path = os.path.join(cache_dir, name)
                    try:
                        os.remove(path)
                        removed += 1
                    except Exception:
                        pass
            return removed

        paths = _paths(cache_dir, ticker or "", interval or "")
        for p in (paths.get("parquet"), paths.get("meta")):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    removed += 1
                except Exception:
                    pass
    except Exception:
        return removed
    return removed