"""Modular institutional momentum scanner package."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .data import normalize_columns

__all__ = ["EntryScanner", "WatchlistScanner", "normalize_columns", "run_dual_mode_scan", "run_scanner"]


def __getattr__(name: str) -> Any:
    if name in {"EntryScanner", "WatchlistScanner"}:
        module = import_module(".modes", __name__)
        return getattr(module, name)
    if name in {"run_dual_mode_scan", "run_scanner"}:
        module = import_module(".scanner", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
