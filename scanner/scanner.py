"""Main scanner orchestration for the modular momentum scanner."""

from __future__ import annotations

import logging
from math import ceil
from typing import Dict, List, Optional

import pandas as pd

from .config import ScannerConfig
from .data import download_history, download_history_batch, get_universe, normalize_columns
from .indicators import pct_change
from .modes import EntryScanner, WatchlistScanner, FilterResult
from .report import format_results, save_results

logger = logging.getLogger(__name__)


WATCHLIST_EXPORT_RENAMES = {
    "ticker": "Ticker",
    "score": "Watchlist Score",
    "sector": "Sector",
    "trend": "Trend",
    "base_score": "Base Score",
    "volume_score": "Volume Score",
    "relative_strength": "Relative Strength",
    "atr_contraction": "ATR Contraction",
    "days_in_consolidation": "Days in Consolidation",
    "trade_quality": "Trade Quality",
    "setup_id": "Setup ID",
    "recommendation": "Recommendation",
    "confidence": "Confidence",
    "reason_text": "Reason Text",
}

ENTRY_EXPORT_RENAMES = {
    "ticker": "Ticker",
    "score": "Entry Score",
    "sector": "Sector",
    "entry_price": "Entry Price",
    "stop_loss": "Stop Loss",
    "risk_pct": "Risk %",
    "target_1": "Target 1",
    "target_2": "Target 2",
    "risk_reward": "Risk Reward",
    "breakout_date": "Breakout Date",
    "breakout_volume_ratio": "Breakout Volume Ratio",
    "trade_quality": "Trade Quality",
    "setup_id": "Setup ID",
    "recommendation": "Recommendation",
    "confidence": "Confidence",
    "reason_text": "Reason Text",
}

def _update_progress(progress_callback, value: float) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(max(0.0, min(1.0, value)))
    except Exception:
        return


def run_dual_mode_scan(
    config: Optional[ScannerConfig] = None,
    output_path: Optional[str] = None,
    progress_callback=None,
) -> Dict[str, pd.DataFrame]:
    """Run both watchlist and entry scanners and return two separate DataFrames."""
    config = config or ScannerConfig()
    logger.info("Starting dual-mode scanner with config %s", config.as_dict())

    universe = get_universe(config)
    if not universe:
        logger.warning("Universe resolution returned no tickers")
        return {"watchlist": pd.DataFrame(), "entry": pd.DataFrame()}

    _update_progress(progress_callback, 0.05)
    watchlist_rows: List[Dict[str, object]] = []
    entry_rows: List[Dict[str, object]] = []
    watchlist_scanner = WatchlistScanner(config)
    entry_scanner = EntryScanner(config)

    # Batch download the scan universe in chunks so the UI can report progress
    # while we wait on network-bound history fetches.
    scan_universe = universe[:150]
    # Small chunks keep the UI responsive and make progress visible while
    # the network-bound history fetch is in flight.
    chunk_size = min(5, max(1, len(scan_universe)))
    total_chunks = max(1, ceil(len(scan_universe) / chunk_size))
    for chunk_index, start in enumerate(range(0, len(scan_universe), chunk_size), start=1):
        chunk = scan_universe[start:start + chunk_size]
        _update_progress(progress_callback, 0.05 + (0.65 * (chunk_index - 1) / total_chunks))
        chunk_map = download_history_batch(chunk, config)

        for ticker in chunk:
            try:
                df = chunk_map.get(ticker)
                if df is None or df.empty:
                    df = download_history(ticker, config)
                if df.empty or len(df) < config.min_candles:
                    continue

                # Sector logic can be enhanced here later
                sector = "Unknown"

                watch_result = watchlist_scanner.evaluate(df, ticker=ticker, sector=sector)
                if watch_result.get("passed"):
                    watchlist_rows.append(watch_result)

                entry_result = entry_scanner.evaluate(df, ticker=ticker, sector=sector)
                if entry_result.get("passed"):
                    entry_rows.append(entry_result)

            except Exception as exc:
                logger.exception("Scanner failed for %s: %s", ticker, exc)

        _update_progress(progress_callback, 0.05 + (0.75 * chunk_index / total_chunks))

    watch_results = pd.DataFrame(watchlist_rows).sort_values(by=["score"], ascending=False) if watchlist_rows else pd.DataFrame()
    entry_results = pd.DataFrame(entry_rows).sort_values(by=["score"], ascending=False) if entry_rows else pd.DataFrame()

    # Rename columns for UI and CSV consistency
    if not watch_results.empty:
        watch_results.rename(columns=WATCHLIST_EXPORT_RENAMES, inplace=True)
    if not entry_results.empty:
        entry_results.rename(columns=ENTRY_EXPORT_RENAMES, inplace=True)

    # Define columns for output files to ensure consistency
    watchlist_cols = list(WATCHLIST_EXPORT_RENAMES.values())
    entry_cols = list(ENTRY_EXPORT_RENAMES.values())

    if not watch_results.empty:
        watch_path = (output_path.replace(".csv", "_watchlist.csv") if output_path else "data/watchlist.csv")
        output_watchlist_cols = [col for col in watchlist_cols if col in watch_results.columns]
        save_results(watch_results, watch_path, columns=output_watchlist_cols)

    if not entry_results.empty:
        entry_path = (output_path.replace(".csv", "_entry.csv") if output_path else "data/entry.csv")
        output_entry_cols = [col for col in entry_cols if col in entry_results.columns]
        save_results(entry_results, entry_path, columns=output_entry_cols)

    # Generate 'rejected.csv' for near-misses
    near_misses = []
    for _, row in watch_results.iterrows():
        if config.watchlist_min_score * 0.9 <= float(row.get("Watchlist Score", 0)) < config.watchlist_min_score:
            near_misses.append({"Ticker": row.get("Ticker"), "Score": row.get("Watchlist Score"), "Missing Criteria": "Watchlist threshold near miss"})
    for _, row in entry_results.iterrows():
        if config.entry_min_score * 0.9 <= float(row.get("Entry Score", 0)) < config.entry_min_score:
            near_misses.append({"Ticker": row.get("Ticker"), "Score": row.get("Entry Score"), "Missing Criteria": "Entry threshold near miss"})

    if near_misses:
        rejected_path = output_path.replace(".csv", "_rejected.csv") if output_path else "data/rejected.csv"
        save_results(pd.DataFrame(near_misses), rejected_path)

    _update_progress(progress_callback, 1.0)
    logger.info("Watchlist candidates: %d | Entry candidates: %d", len(watch_results), len(entry_results))
    return {"watchlist": watch_results, "entry": entry_results}

def run_scanner(config: Optional[ScannerConfig] = None, output_path: Optional[str] = None) -> pd.DataFrame:
    """Compatibility wrapper returning the actionable entry results DataFrame."""
    results = run_dual_mode_scan(config=config, output_path=output_path)
    return results.get("entry", pd.DataFrame())


def run_from_cli() -> None:
    """CLI entrypoint for running the scanner from the terminal."""
    results = run_scanner()
    print(format_results(results))
