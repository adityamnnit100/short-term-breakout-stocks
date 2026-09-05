"""Run a single-ticker diagnostics evaluation from a CSV file.

Usage:
  python -m scanner.diagnostics_runner path/to/history.csv TICKER.NS [--mode=Entry|Watchlist]

This loads the CSV, normalizes columns, runs the quality, setup, transition and trigger
engines, and prints a JSON-friendly report of scores, reasons and module metrics.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict

import pandas as pd

from .config import ScannerConfig
from .data import normalize_columns
from .modes import EntryScanner, WatchlistScanner

logger = logging.getLogger("AlphaScanner.DiagnosticsRunner")


def analyze_csv(path: str, ticker: str, scan_mode: str = "Entry") -> Dict[str, object]:
    cfg = ScannerConfig()
    df = pd.read_csv(path)
    df = normalize_columns(df)

    if df is None or df.empty:
        raise ValueError("No data loaded from CSV")

    if scan_mode.lower().startswith("watch"):
        scanner = WatchlistScanner(cfg)
    else:
        scanner = EntryScanner(cfg)

    prep = scanner.prepare_shared_evaluation(df, ticker=ticker, sector="Unknown")
    prepared = prep.get("prepared")
    context = prep.get("context")

    if prepared is None or prepared.empty or context is None:
        return {"ticker": ticker, "error": "Insufficient data after preparation"}

    result = scanner.evaluate(df, ticker=ticker, sector="Unknown", prepared=prepared, context=context)

    # Extract module-level details where present
    report = {
        "ticker": ticker,
        "scan_mode": scan_mode,
        "passed": bool(result.get("passed", False)),
        "score": result.get("score"),
        "reason_label": result.get("reason_label"),
        "reasons": result.get("reasons", []),
        "quality": result.get("quality", {}),
        "setup_result": result.get("setup_result", {}),
        "transition_result": result.get("transition_result", {}),
        "trigger_result": result.get("trigger_result", {}),
        "common_results": result.get("common_results", {}),
    }
    return report


def _main():
    p = argparse.ArgumentParser(description="Run diagnostics on a CSV history file for one ticker")
    p.add_argument("csv", help="Path to CSV file with OHLCV columns")
    p.add_argument("ticker", help="Ticker symbol with exchange suffix (e.g., RELIANCE.NS)")
    p.add_argument("--mode", choices=["Entry", "Watchlist"], default="Entry", help="Scanner mode to evaluate")
    args = p.parse_args()

    try:
        report = analyze_csv(args.csv, args.ticker, scan_mode=args.mode)
        print(json.dumps(report, indent=2, default=str))
    except Exception as exc:
        logger.exception("Diagnostics run failed: %s", exc)
        print(json.dumps({"error": str(exc)}))


if __name__ == "__main__":
    _main()
