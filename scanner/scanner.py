"""Main scanner orchestration for the modular momentum scanner."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional
import concurrent.futures
from threading import Lock
from datetime import datetime

import pandas as pd

from .config import ScannerConfig
from .data import download_history_batch, get_universe
from .modes import EntryScanner, WatchlistScanner
from .exports import ENTRY_EXPORT_RENAMES, WATCHLIST_EXPORT_RENAMES, export_scan_results
from .report import format_results
from quality_filter import QualityFilterEngine
from setup_engine import SetupEngine
from trigger_engine import TriggerEngine

logger = logging.getLogger("AlphaScanner.Scanner")


def _update_progress(progress_callback, value: float) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(max(0.0, min(1.0, value)))
    except Exception:
        return


def _in_streamlit_runtime() -> bool:
    """Return True when the scanner is running inside a Streamlit script context."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return False

    try:
        return get_script_run_ctx(suppress_warning=True) is not None
    except TypeError:
        # Older Streamlit versions may not support suppress_warning.
        try:
            return get_script_run_ctx() is not None
        except Exception:
            return False
    except Exception:
        return False


def _suppress_streamlit_context_warning() -> None:
    """Mute the noisy ScriptRunContext warning in bare/CLI execution."""
    for name in (
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.scriptrunner",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


def run_dual_mode_scan(
    config: Optional[ScannerConfig] = None,
    output_path: Optional[str] = None,
    progress_callback=None,
    use_cache: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Run both watchlist and entry scanners and return two separate DataFrames."""
    config = config or ScannerConfig()
    if not _in_streamlit_runtime():
        _suppress_streamlit_context_warning()
    logger.info("Starting dual-mode scanner with config %s", config.as_dict())
    logger.debug(
        "Dual-mode scan requested with universe=%s interval=%s min_candles=%s use_cache=%s",
        config.universe,
        config.interval,
        config.min_candles,
        use_cache,
    )

    universe = get_universe(config)
    if not universe:
        logger.warning("Universe resolution returned no tickers")
        return {"watchlist": pd.DataFrame(), "entry": pd.DataFrame()}
    logger.debug("Resolved universe size=%s head=%s", len(universe), universe[:5])

    _update_progress(progress_callback, 0.05)
    watchlist_rows: List[Dict[str, object]] = []
    entry_rows: List[Dict[str, object]] = []
    entry_candidate_rows: List[Dict[str, object]] = []
    setup_rows: List[Dict[str, object]] = []
    transition_rows: List[Dict[str, object]] = []
    trigger_rows: List[Dict[str, object]] = []
    rows_lock = Lock()
    quality_engine = QualityFilterEngine(config)
    setup_engine = SetupEngine(config)
    from transition_engine import TransitionEngine

    transition_engine = TransitionEngine(config)
    trigger_engine = TriggerEngine(config)
    watchlist_scanner = WatchlistScanner(config, quality_engine=quality_engine, setup_engine=setup_engine, transition_engine=transition_engine, trigger_engine=trigger_engine, scan_mode="Watchlist")
    entry_scanner = EntryScanner(config, quality_engine=quality_engine, setup_engine=setup_engine, transition_engine=transition_engine, trigger_engine=trigger_engine, scan_mode="Entry")

    _update_progress(progress_callback, 0.1)
    logger.info("Downloading history for %d tickers...", len(universe))
    # Download all history in one go. The underlying cache and batching will handle efficiency.
    history_map = download_history_batch(universe, config, use_cache=use_cache)
    logger.info("Downloaded history for %d tickers.", len(history_map))
    _update_progress(progress_callback, 0.75)

    processed_count = 0
    total_tickers = len(history_map)

    def _process_ticker(ticker: str) -> None:
        nonlocal processed_count
        try:
            df = history_map.get(ticker)
            if df is None or df.empty or len(df) < config.min_candles:
                return

            # Sector logic can be enhanced here later
            sector = "Unknown"
            prepared = watchlist_scanner._prepare_df(df)
            if prepared.empty or len(prepared) < config.min_candles:
                return
            context = quality_engine.build_context(prepared, ticker=ticker, sector=sector)
            if context is None:
                return

            watch_result = watchlist_scanner.evaluate(df, ticker=ticker, sector=sector, prepared=prepared, context=context)
            if watch_result.get("passed"):
                with rows_lock:
                    watchlist_rows.append(watch_result)
                    setup_rows.append({
                        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                        "ticker": watch_result.get("Ticker") or watch_result.get("ticker"),
                        "scan_mode": "Watchlist",
                        "setup_score": watch_result.get("setup_score", 0.0),
                        "base_score": watch_result.get("setup_base_score", 0.0),
                        "compression_score": watch_result.get("setup_compression_score", 0.0),
                        "volume_score": watch_result.get("setup_volume_score", 0.0),
                        "resistance_score": watch_result.get("setup_resistance_score", 0.0),
                        "structure_score": watch_result.get("setup_structure_score", 0.0),
                        "risk_score": watch_result.get("setup_risk_score", 0.0),
                        "category": watch_result.get("setup_category", "Poor"),
                        "reasons": watch_result.get("setup_reasons", []),
                        "weaknesses": watch_result.get("setup_weaknesses", []),
                    })
                    transition_rows.append({
                        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                        "ticker": watch_result.get("Ticker") or watch_result.get("ticker"),
                        "scan_mode": "Watchlist",
                        "transition_score": watch_result.get("transition_score", 0.0),
                        "transition_category": watch_result.get("transition_category", "Weak"),
                        "transition_setup_velocity_score": watch_result.get("transition_setup_velocity_score", 0.0),
                        "transition_rs_acceleration_score": watch_result.get("transition_rs_acceleration_score", 0.0),
                        "transition_volume_transition_score": watch_result.get("transition_volume_transition_score", 0.0),
                        "transition_compression_evolution_score": watch_result.get("transition_compression_evolution_score", 0.0),
                        "transition_resistance_pressure_score": watch_result.get("transition_resistance_pressure_score", 0.0),
                        "transition_price_acceptance_score": watch_result.get("transition_price_acceptance_score", 0.0),
                        "transition_opportunity_velocity_score": watch_result.get("transition_opportunity_velocity_score", 0.0),
                        "transition_reasons": watch_result.get("transition_reasons", []),
                        "transition_weaknesses": watch_result.get("transition_weaknesses", []),
                        "transition_qualifies": watch_result.get("transition_qualifies", False),
                        "transition_metrics": watch_result.get("transition_metrics", {}),
                    })
                    trigger_rows.append({
                        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                        "ticker": watch_result.get("Ticker") or watch_result.get("ticker"),
                        "scan_mode": "Watchlist",
                        "trigger_decision": watch_result.get("trigger_decision", "WAIT"),
                        "trigger_confidence": watch_result.get("trigger_confidence", "Low"),
                        "trigger_score": watch_result.get("trigger_score", 0.0),
                        "trigger_qualifies": watch_result.get("trigger_qualifies", False),
                        "trigger_reasons": watch_result.get("trigger_reasons", []),
                        "trigger_weaknesses": watch_result.get("trigger_weaknesses", []),
                        "trigger_module_results": watch_result.get("trigger_module_results", {}),
                        "trigger_metrics": watch_result.get("trigger_metrics", {}),
                    })

            entry_result = entry_scanner.evaluate(df, ticker=ticker, sector=sector, prepared=prepared, context=context)
            with rows_lock:
                entry_candidate_rows.append(entry_result)

        except Exception as exc:
            logger.exception("Scanner failed for %s: %s", ticker, exc)
        finally:
            with rows_lock:
                processed_count += 1
            if progress_callback and total_tickers > 0:
                _update_progress(progress_callback, 0.75 + (0.20 * (processed_count / total_tickers)))

    logger.info("Processing %d tickers...", total_tickers)
    # Use a single ThreadPoolExecutor to process all tickers in parallel.
    max_workers = max(1, int(getattr(config, "scan_max_workers", 8) or 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(_process_ticker, history_map.keys())

    watch_results = pd.DataFrame(watchlist_rows).sort_values(by=["score"], ascending=False) if watchlist_rows else pd.DataFrame()
    ranked_entry_rows = trigger_engine.rank_candidate_rows(entry_candidate_rows)
    entry_final_rows = [row for row in ranked_entry_rows if row.get("passed")]

    if entry_final_rows:
        for row in entry_final_rows:
            entry_rows.append(row)
            setup_rows.append({
                "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                "ticker": row.get("Ticker") or row.get("ticker"),
                "scan_mode": "Entry",
                "setup_score": row.get("setup_score", 0.0),
                "base_score": row.get("setup_base_score", 0.0),
                "compression_score": row.get("setup_compression_score", 0.0),
                "volume_score": row.get("setup_volume_score", 0.0),
                "resistance_score": row.get("setup_resistance_score", 0.0),
                "structure_score": row.get("setup_structure_score", 0.0),
                "risk_score": row.get("setup_risk_score", 0.0),
                "category": row.get("setup_category", "Poor"),
                "reasons": row.get("setup_reasons", []),
                "weaknesses": row.get("setup_weaknesses", []),
            })
            transition_rows.append({
                "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                "ticker": row.get("Ticker") or row.get("ticker"),
                "scan_mode": "Entry",
                "transition_score": row.get("transition_score", 0.0),
                "transition_category": row.get("transition_category", "Weak"),
                "transition_setup_velocity_score": row.get("transition_setup_velocity_score", 0.0),
                "transition_rs_acceleration_score": row.get("transition_rs_acceleration_score", 0.0),
                "transition_volume_transition_score": row.get("transition_volume_transition_score", 0.0),
                "transition_compression_evolution_score": row.get("transition_compression_evolution_score", 0.0),
                "transition_resistance_pressure_score": row.get("transition_resistance_pressure_score", 0.0),
                "transition_price_acceptance_score": row.get("transition_price_acceptance_score", 0.0),
                "transition_opportunity_velocity_score": row.get("transition_opportunity_velocity_score", 0.0),
                "transition_reasons": row.get("transition_reasons", []),
                "transition_weaknesses": row.get("transition_weaknesses", []),
                "transition_qualifies": row.get("transition_qualifies", False),
                "transition_metrics": row.get("transition_metrics", {}),
            })
            trigger_rows.append({
                "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                "ticker": row.get("Ticker") or row.get("ticker"),
                "scan_mode": "Entry",
                "trigger_decision": row.get("trigger_decision", "WAIT"),
                "trigger_confidence": row.get("trigger_confidence", "Low"),
                "trigger_score": row.get("trigger_score", 0.0),
                "trigger_priority_score": row.get("trigger_priority_score", 0.0),
                "trigger_rank_percentile": row.get("trigger_rank_percentile", 100.0),
                "trigger_qualifies": row.get("trigger_qualifies", False),
                "trigger_reasons": row.get("trigger_reasons", []),
                "trigger_weaknesses": row.get("trigger_weaknesses", []),
                "trigger_module_results": row.get("trigger_module_results", {}),
                "trigger_metrics": row.get("trigger_metrics", {}),
            })

    entry_results = pd.DataFrame(entry_rows).sort_values(by=["score"], ascending=False) if entry_rows else pd.DataFrame()
    logger.debug(
        "Dual-mode scan finished: watchlist_rows=%s entry_rows=%s",
        len(watch_results),
        len(entry_results),
    )

    if not watch_results.empty:
        watch_results.rename(columns=WATCHLIST_EXPORT_RENAMES, inplace=True)
    if not entry_results.empty:
        entry_results.rename(columns=ENTRY_EXPORT_RENAMES, inplace=True)

    export_scan_results(watch_results, entry_results, config, output_path=output_path)

    if setup_rows:
        try:
            from alphascanner_ui.database import append_setup_analysis_rows

            append_setup_analysis_rows(setup_rows)
        except Exception as exc:
            logger.warning("Failed to persist setup analysis rows: %s", exc)

    if transition_rows:
        try:
            from alphascanner_ui.database import append_transition_analysis_rows

            append_transition_analysis_rows(transition_rows)
        except Exception as exc:
            logger.warning("Failed to persist transition analysis rows: %s", exc)

    if trigger_rows:
        try:
            from alphascanner_ui.database import append_trigger_analysis_rows

            append_trigger_analysis_rows(trigger_rows)
        except Exception as exc:
            logger.warning("Failed to persist trigger analysis rows: %s", exc)

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
