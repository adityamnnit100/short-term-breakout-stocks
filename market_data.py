"""Shared offline market-data helpers.

This module centralizes the repo-local data sources used by the scanner and UI:
cached symbol universes, cached sector mappings, and cached institutional flow.
It intentionally avoids NSE network calls so the app can operate in offline or
rate-limited environments.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parent
CACHE_DIR = ROOT_DIR / "data" / "cache"
SECTOR_MAPPING_FILE = CACHE_DIR / "sector_mapping.json"
SYSTEM_CACHE_DB = ROOT_DIR / "breakout_history.db"

_DEFAULT_FLOW = {
    "date": "N/A",
    "fii_net": 0.0,
    "dii_net": 0.0,
    "fii_buy": 0.0,
    "fii_sell": 0.0,
    "dii_buy": 0.0,
    "dii_sell": 0.0,
}


def _normalize_cached_symbol(stem: str) -> Optional[str]:
    if not stem.startswith("yf_"):
        return None

    symbol = stem[3:]
    for suffix in ("_1d", "_1wk", "_1mo", "_60m", "_30m", "_15m", "_5m", "_1h", "_4h", "_90m", "_2m", "_1m"):
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]
            break

    if symbol.endswith("_NS"):
        return f"{symbol[:-3]}.NS"
    return symbol or None


@lru_cache(maxsize=1)
def _load_cached_symbol_set() -> Tuple[str, ...]:
    if not CACHE_DIR.exists():
        return tuple()

    symbols = {
        symbol
        for path in CACHE_DIR.glob("yf_*.pkl")
        for symbol in [_normalize_cached_symbol(path.stem)]
        if symbol
    }
    return tuple(sorted(symbols))


@lru_cache(maxsize=4)
def _load_sector_payload() -> dict:
    if not SECTOR_MAPPING_FILE.exists():
        return {}

    try:
        payload = json.loads(SECTOR_MAPPING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    return payload if isinstance(payload, dict) else {}


def _load_system_cache_value(key: str) -> Optional[str]:
    if not SYSTEM_CACHE_DB.exists():
        return None

    try:
        conn = sqlite3.connect(SYSTEM_CACHE_DB)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM system_cache WHERE key = ? ORDER BY updated_at DESC LIMIT 1",
                (key,),
            )
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception:
        return None


@lru_cache(maxsize=8)
def _load_sector_mapping_cached(universe_type: str = "Nifty 500") -> dict:
    payload = _load_sector_payload()
    cached = payload.get(universe_type, {})
    if isinstance(cached, dict):
        mapping = cached.get("mapping", {})
        if isinstance(mapping, dict):
            return {str(symbol): str(sector) for symbol, sector in mapping.items() if symbol}
    return {}


def load_sector_mapping(universe_type: str = "Nifty 500") -> dict:
    return dict(_load_sector_mapping_cached(universe_type))


@lru_cache(maxsize=8)
def load_symbol_universe(universe_type: str = "Nifty 500") -> Tuple[str, ...]:
    cached_symbols = _load_cached_symbol_set()
    sector_mapping = load_sector_mapping(universe_type)

    if universe_type == "Total Market (Cap Focused)":
        symbols = set(cached_symbols)
        symbols.update(sector_mapping.keys())
        return tuple(sorted(symbols))

    if sector_mapping:
        return tuple(sorted(sector_mapping.keys()))

    if cached_symbols:
        return tuple(sorted(cached_symbols[:500]))

    return tuple()


@lru_cache(maxsize=8)
def _load_institutional_flow_cached() -> dict:
    cached = _load_system_cache_value("fii_dii_activity")
    if not cached:
        return dict(_DEFAULT_FLOW)

    try:
        payload = json.loads(cached)
    except Exception:
        return dict(_DEFAULT_FLOW)

    if not isinstance(payload, dict):
        return dict(_DEFAULT_FLOW)

    flow = dict(_DEFAULT_FLOW)
    for key in ("fii_net", "dii_net", "fii_buy", "fii_sell", "dii_buy", "dii_sell"):
        try:
            flow[key] = float(payload.get(key, 0) or 0)
        except Exception:
            flow[key] = 0.0
    flow["date"] = str(payload.get("date", "N/A") or "N/A")
    return flow


def load_institutional_flow() -> dict:
    return dict(_load_institutional_flow_cached())
