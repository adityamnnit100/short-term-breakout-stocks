"""Main scanner orchestration for the modular momentum scanner."""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional
import concurrent.futures
import threading
from threading import Lock
from datetime import datetime

# Correctly import Streamlit context functions. This allows worker threads to
# interact with the Streamlit frontend (e.g., for progress bars).
try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
except ImportError:
    # Fallback for older Streamlit versions
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import (
            add_script_run_ctx,
            get_script_run_ctx,
        )
    except ImportError:
        # If streamlit is not installed, these will be None.
        get_script_run_ctx = None
        add_script_run_ctx = None

import pandas as pd

from .config import ScannerConfig
from .data import download_history_batch, get_universe
from .modes import EntryScanner, WatchlistScanner, ShortTermScanner
from .exports import ENTRY_EXPORT_RENAMES, WATCHLIST_EXPORT_RENAMES, export_scan_results
from .report import format_results
from .diagnostics import DiagnosticsCollector
from quality_filter import QualityFilterEngine
from setup_engine import SetupEngine
from transition_engine import TransitionEngine
from trigger_engine import TriggerEngine

logger = logging.getLogger("AlphaScanner.Scanner")


def _process_ticker_worker(args):
    """Worker function executed in a separate process to evaluate a single ticker.

    Args is a tuple (ticker, df, config) where df is a pandas DataFrame and
    config is a ScannerConfig dataclass instance (picklable).
    """
    try:
        ticker, df, config = args
        # Local imports to avoid cross-process import issues and to ensure each
        # process constructs its own engine instances.
        from quality_filter import QualityFilterEngine
        from setup_engine import SetupEngine
        from transition_engine import TransitionEngine
        from trigger_engine import TriggerEngine
        from .modes import WatchlistScanner, EntryScanner

        quality_engine = QualityFilterEngine(config)
        setup_engine = SetupEngine(config)
        transition_engine = TransitionEngine(config)
        trigger_engine = TriggerEngine(config)

        watchlist_scanner = WatchlistScanner(
            config,
            quality_engine=quality_engine,
            setup_engine=setup_engine,
            transition_engine=transition_engine,
            trigger_engine=trigger_engine,
            scan_mode="Watchlist",
        )
        entry_scanner = EntryScanner(
            config,
            quality_engine=quality_engine,
            setup_engine=setup_engine,
            transition_engine=transition_engine,
            trigger_engine=trigger_engine,
            scan_mode="Entry",
        )

        sector = "Unknown"
        shared_components = watchlist_scanner.prepare_shared_evaluation(df, ticker=ticker, sector=sector)
        prepared = shared_components.get("prepared")
        context = shared_components.get("context")
        if prepared is None or prepared.empty or len(prepared) < config.min_candles:
            return {"ticker": ticker, "watch": None, "entry": None}

        watch_result = watchlist_scanner.evaluate(df, ticker=ticker, sector=sector, prepared=prepared, context=context)
        entry_result = entry_scanner.evaluate(df, ticker=ticker, sector=sector, prepared=prepared, context=context)
        return {"ticker": ticker, "watch": watch_result, "entry": entry_result}
    except Exception as exc:  # pragma: no cover - runtime dependent
        return {"ticker": args[0] if isinstance(args, (list, tuple)) and args else None, "error": str(exc)}



def _update_progress(progress_callback, value: float) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(max(0.0, min(1.0, value)))
    except Exception:
        return


def _prefilter_universe_by_market_cap(
    universe: List[str], config: ScannerConfig
) -> List[str]:
    """
    Filters the universe based on market capitalization before downloading
    full history, to improve performance on large universes.
    """
    min_cap = getattr(config, "quality_min_market_cap_cr", 0.0)
    max_cap = getattr(config, "quality_max_market_cap_cr", 0.0)

    if min_cap <= 0 and max_cap <= 0:
        # No market cap filter is configured, so no pre-filtering is possible.
        return universe

    logger.info(
        "Prefiltering universe of %d tickers by market cap (Min: %s Cr, Max: %s Cr)...",
        len(universe), min_cap, max_cap if max_cap > 0 else "inf"
    )

    try:
        # Use the existing metadata caching infrastructure from breakout.py
        from breakout import prefetch_metadata, get_all_metadata_cache
    except ImportError:
        logger.warning("Could not import breakout.py; skipping market cap pre-filter.")
        return universe

    # Ensure the cache is populated for the given universe. This is fast.
    prefetch_metadata(universe)
    metadata_cache = get_all_metadata_cache(universe, expiry_hours=24)

    if not metadata_cache:
        logger.warning("Metadata cache is empty; cannot pre-filter by market cap.")
        return universe

    filtered_universe = []
    for ticker in universe:
        market_cap_cr, _ = metadata_cache.get(ticker, (None, None))

        # If metadata is missing, include it to be safe. It will be filtered later.
        # Otherwise, check if it falls within the configured min/max cap range.
        if market_cap_cr is None or ((min_cap <= 0 or market_cap_cr >= min_cap) and (max_cap <= 0 or market_cap_cr <= max_cap)):
            filtered_universe.append(ticker)

    logger.info(
        "Market cap pre-filter reduced universe from %d to %d tickers.",
        len(universe), len(filtered_universe)
    )
    return filtered_universe

def _create_setup_row(result: Dict[str, Any], scan_mode: str) -> Dict[str, Any]:
    """Creates a dictionary for the setup analysis results from a scanner result."""
    return {
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": result.get("Ticker") or result.get("ticker"),
        "scan_mode": scan_mode,
        "setup_score": result.get("setup_score", 0.0),
        "base_score": result.get("setup_base_score", 0.0),
        "compression_score": result.get("setup_compression_score", 0.0),
        "volume_score": result.get("setup_volume_score", 0.0),
        "resistance_score": result.get("setup_resistance_score", 0.0),
        "structure_score": result.get("setup_structure_score", 0.0),
        "risk_score": result.get("setup_risk_score", 0.0),
        "category": result.get("setup_category", "Poor"),
        "reasons": result.get("setup_reasons", []),
        "weaknesses": result.get("setup_weaknesses", []),
    }


def _create_transition_row(result: Dict[str, Any], scan_mode: str) -> Dict[str, Any]:
    """Creates a dictionary for the transition analysis results from a scanner result."""
    return {
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": result.get("Ticker") or result.get("ticker"),
        "scan_mode": scan_mode,
        "transition_score": result.get("transition_score", 0.0),
        "transition_category": result.get("transition_category", "Weak"),
        "transition_setup_velocity_score": result.get("transition_setup_velocity_score", 0.0),
        "transition_rs_acceleration_score": result.get("transition_rs_acceleration_score", 0.0),
        "transition_volume_transition_score": result.get("transition_volume_transition_score", 0.0),
        "transition_compression_evolution_score": result.get("transition_compression_evolution_score", 0.0),
        "transition_resistance_pressure_score": result.get("transition_resistance_pressure_score", 0.0),
        "transition_price_acceptance_score": result.get("transition_price_acceptance_score", 0.0),
        "transition_opportunity_velocity_score": result.get("transition_opportunity_velocity_score", 0.0),
        "transition_reasons": result.get("transition_reasons", []),
        "transition_weaknesses": result.get("transition_weaknesses", []),
        "transition_qualifies": result.get("transition_qualifies", False),
        "transition_metrics": result.get("transition_metrics", {}),
    }


def _create_trigger_row(result: Dict[str, Any], scan_mode: str) -> Dict[str, Any]:
    """Creates a dictionary for the trigger analysis results from a scanner result."""
    return {
        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": result.get("Ticker") or result.get("ticker"),
        "scan_mode": scan_mode,
        "trigger_decision": result.get("trigger_decision", "WAIT"),
        "trigger_confidence": result.get("trigger_confidence", "Low"),
        "trigger_score": result.get("trigger_score", 0.0),
        "trigger_priority_score": result.get("trigger_priority_score", 0.0),
        "trigger_rank_percentile": result.get("trigger_rank_percentile", 100.0),
        "trigger_qualifies": result.get("trigger_qualifies", False),
        "trigger_reasons": result.get("trigger_reasons", []),
        "trigger_weaknesses": result.get("trigger_weaknesses", []),
        "trigger_module_results": result.get("trigger_module_results", {}),
        "trigger_metrics": result.get("trigger_metrics", {}),
    }

def run_dual_mode_scan(
    config: Optional[ScannerConfig] = None,
    output_path: Optional[str] = None,
    progress_callback=None,
    use_cache: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Run both watchlist and entry scanners and return two separate DataFrames."""
    config = config or ScannerConfig()
    scan_started_at = time.perf_counter()

    # Capture the Streamlit context from the main thread. This will be passed
    # to the worker threads so they can update the UI (e.g., progress bar).
    main_thread_ctx = get_script_run_ctx() if get_script_run_ctx else None

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
    logger.info("Universe resolution finished in %.2fs for %s", time.perf_counter() - scan_started_at, config.universe)

    # Pre-filter the universe by market cap to avoid downloading history for stocks that will be rejected anyway.
    prefilter_started_at = time.perf_counter()
    universe = _prefilter_universe_by_market_cap(universe, config)
    logger.info(
        "Market-cap prefilter finished in %.2fs and left %s tickers",
        time.perf_counter() - prefilter_started_at,
        len(universe),
    )

    _update_progress(progress_callback, 0.05)
    watchlist_rows: List[Dict[str, object]] = []
    entry_rows: List[Dict[str, object]] = []
    entry_candidate_rows: List[Dict[str, object]] = []
    setup_rows: List[Dict[str, object]] = []
    transition_rows: List[Dict[str, object]] = []
    trigger_rows: List[Dict[str, object]] = []
    rows_lock = Lock()
    history_cache_lock = Lock()
    transition_history_cache: Dict[tuple, tuple] = {}
    trigger_history_cache: Dict[tuple, tuple] = {}

    def _cached_history_loader(cache: Dict[tuple, tuple], loader):
        def _load(ticker: str, scan_mode: str, limit: int):
            cache_key = (ticker, scan_mode, limit)
            with history_cache_lock:
                cached_rows = cache.get(cache_key)
            if cached_rows is not None:
                return [dict(row) for row in cached_rows]

            rows = tuple(dict(row) for row in loader(ticker, scan_mode, limit))
            with history_cache_lock:
                cache[cache_key] = rows
            return [dict(row) for row in rows]

        return _load

    diagnostics = DiagnosticsCollector(
        config=config,
        enabled=bool(getattr(config, "diagnostics_enabled", False)),
        top_rules=int(getattr(config, "diagnostics_top_rules", 3) or 3),
    )
    quality_engine = QualityFilterEngine(config)
    setup_engine = SetupEngine(config)
    transition_engine = TransitionEngine(config)
    transition_engine.history_loader = _cached_history_loader(transition_history_cache, transition_engine.history_loader)
    trigger_engine = TriggerEngine(config)
    trigger_engine.history_loader = _cached_history_loader(trigger_history_cache, trigger_engine.history_loader)
    watchlist_scanner = WatchlistScanner(config, quality_engine=quality_engine, setup_engine=setup_engine, transition_engine=transition_engine, trigger_engine=trigger_engine, scan_mode="Watchlist")
    # Use ShortTermScanner when intraday confirmation gates are enabled
    if bool(getattr(config, "trigger_enable_intraday_confirmation", False)):
        entry_scanner = ShortTermScanner(config, quality_engine=quality_engine, setup_engine=setup_engine, transition_engine=transition_engine, trigger_engine=trigger_engine, scan_mode="Entry")
    else:
        entry_scanner = EntryScanner(config, quality_engine=quality_engine, setup_engine=setup_engine, transition_engine=transition_engine, trigger_engine=trigger_engine, scan_mode="Entry")

    _update_progress(progress_callback, 0.1)
    logger.info("Downloading history for %d tickers...", len(universe))
    # Download all history in one go. The underlying cache and batching will handle efficiency.
    history_started_at = time.perf_counter()
    history_map = download_history_batch(universe, config, use_cache=use_cache)
    logger.info(
        "History download finished in %.2fs for %d tickers",
        time.perf_counter() - history_started_at,
        len(universe),
    )
    history_download_time = time.perf_counter() - history_started_at
    logger.info("Downloaded history for %d tickers.", len(history_map))
    diagnostics.record_universe(len(universe))
    _update_progress(progress_callback, 0.75)

    processed_count = 0
    total_tickers = len(history_map)
    per_ticker_times: List[float] = []
    per_ticker_lock = Lock()

    def _process_ticker(ticker: str) -> None:
        nonlocal processed_count
        try:
            t0 = time.perf_counter()
            # Attach the captured context to the current worker thread.
            if main_thread_ctx and add_script_run_ctx:
                add_script_run_ctx(ctx=main_thread_ctx)

            df = history_map.get(ticker)
            if df is None or df.empty or len(df) < config.min_candles:
                return

            # Sector logic can be enhanced here later
            sector = "Unknown"
            shared_components = watchlist_scanner.prepare_shared_evaluation(df, ticker=ticker, sector=sector)
            prepared = shared_components.get("prepared")
            context = shared_components.get("context")
            if prepared is None or prepared.empty or len(prepared) < config.min_candles:
                return
            if context is None:
                return
            watch_result = watchlist_scanner.evaluate(
                df,
                ticker=ticker,
                sector=sector,
                prepared=prepared,
                context=context,
            )
            if watch_result.get("passed"):
                with rows_lock:
                    watchlist_rows.append(watch_result)
                    setup_rows.append(_create_setup_row(watch_result, "Watchlist"))
                    transition_rows.append(_create_transition_row(watch_result, "Watchlist"))
                    trigger_rows.append(_create_trigger_row(watch_result, "Watchlist"))

            entry_result = entry_scanner.evaluate(
                df,
                ticker=ticker,
                sector=sector,
                prepared=prepared,
                context=context,
            )
            with rows_lock:
                entry_candidate_rows.append(entry_result)
            diagnostics.record_result(entry_result)

        except Exception as exc:
            logger.exception("Scanner failed for %s: %s", ticker, exc)
        finally:
            with rows_lock: # noqa
                processed_count += 1
            t1 = time.perf_counter()
            try:
                with per_ticker_lock:
                    per_ticker_times.append(t1 - t0)
            except Exception:
                pass
            if progress_callback and total_tickers > 0:
                _update_progress(progress_callback, 0.75 + (0.20 * (processed_count / total_tickers)))

    logger.info("Processing %d tickers...", total_tickers)
    # Decide whether to use process-based parallelism to bypass the GIL for
    # CPU-heavy per-ticker evaluation.
    use_process_pool = bool(getattr(config, "scan_use_process_pool", False))
    eval_started_at = time.perf_counter()
    if use_process_pool:
        proc_workers = int(getattr(config, "scan_process_workers", 0) or 0)
        if proc_workers <= 0:
            proc_workers = max(1, min(len(history_map), (os.cpu_count() or 1)))
        logger.info("Using ProcessPoolExecutor with %d workers for ticker evaluation", proc_workers)
        with concurrent.futures.ProcessPoolExecutor(max_workers=proc_workers) as executor:
            # submit (ticker, df, config) tuples; DataFrame and config will be pickled
            futures = {executor.submit(_process_ticker_worker, (ticker, history_map[ticker], config)): ticker for ticker in history_map.keys()}
            for future in concurrent.futures.as_completed(futures):
                ticker = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.exception("Process worker failed for %s: %s", ticker, exc)
                    continue
                if not result:
                    continue
                if result.get("error"):
                    logger.debug("Process worker error for %s: %s", ticker, result.get("error"))
                    continue
                watch_result = result.get("watch")
                entry_result = result.get("entry")
                try:
                    if watch_result and watch_result.get("passed"):
                        with rows_lock:
                            watchlist_rows.append(watch_result)
                            setup_rows.append(_create_setup_row(watch_result, "Watchlist"))
                            transition_rows.append(_create_transition_row(watch_result, "Watchlist"))
                            trigger_rows.append(_create_trigger_row(watch_result, "Watchlist"))
                    if entry_result is not None:
                        with rows_lock:
                            entry_candidate_rows.append(entry_result)
                        diagnostics.record_result(entry_result)
                except Exception:
                    logger.exception("Failed to merge worker result for %s", ticker)
    else:
        # Use a single ThreadPoolExecutor to process all tickers in parallel.
        max_workers = max(1, int(getattr(config, "scan_max_workers", 8) or 8))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(_process_ticker, history_map.keys())

    logger.info(
        "Ticker evaluation finished in %.2fs for %d tickers",
        time.perf_counter() - eval_started_at,
        total_tickers,
    )
    eval_time = time.perf_counter() - eval_started_at

    watch_results = pd.DataFrame(watchlist_rows).sort_values(by=["score"], ascending=False) if watchlist_rows else pd.DataFrame()
    ranked_entry_rows = trigger_engine.rank_candidate_rows(entry_candidate_rows)
    entry_final_rows = [row for row in ranked_entry_rows if row.get("passed")]

    if entry_final_rows:
        for row in entry_final_rows:
            entry_rows.append(row)
            setup_rows.append(_create_setup_row(row, "Entry"))
            transition_rows.append(_create_transition_row(row, "Entry"))
            trigger_rows.append(_create_trigger_row(row, "Entry"))

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

    diagnostics_summary = diagnostics.build_summary()
    if diagnostics_summary:
        logger.info("Scanner diagnostics summary:\n%s", diagnostics.format_summary())
        if bool(getattr(config, "diagnostics_persist", True)):
            try:
                from alphascanner_ui.database import append_diagnostics_rejections, append_diagnostics_run
                p0 = time.perf_counter()
                append_diagnostics_run(
                    {
                        "analysis_date": datetime.now().strftime("%Y-%m-%d"),
                        "universe": config.universe,
                        "summary": diagnostics_summary,
                    }
                )
                append_diagnostics_rejections(diagnostics_summary.get("rejections", []))
                p1 = time.perf_counter()
                persist_diag_time = p1 - p0
            except Exception as exc:
                logger.warning("Failed to persist diagnostics summary: %s", exc)
                persist_diag_time = 0.0

    if setup_rows:
        try:
            from alphascanner_ui.database import append_setup_analysis_rows
            p0 = time.perf_counter()
            append_setup_analysis_rows(setup_rows)
            p1 = time.perf_counter()
            persist_setup_time = p1 - p0
        except Exception as exc:
            logger.warning("Failed to persist setup analysis rows: %s", exc)
            persist_setup_time = 0.0

    if transition_rows:
        try:
            from alphascanner_ui.database import append_transition_analysis_rows
            p0 = time.perf_counter()
            append_transition_analysis_rows(transition_rows)
            p1 = time.perf_counter()
            persist_transition_time = p1 - p0
        except Exception as exc:
            logger.warning("Failed to persist transition analysis rows: %s", exc)
            persist_transition_time = 0.0

    if trigger_rows:
        try:
            from alphascanner_ui.database import append_trigger_analysis_rows
            p0 = time.perf_counter()
            append_trigger_analysis_rows(trigger_rows)
            p1 = time.perf_counter()
            persist_trigger_time = p1 - p0
        except Exception as exc:
            logger.warning("Failed to persist trigger analysis rows: %s", exc)
            persist_trigger_time = 0.0

    _update_progress(progress_callback, 1.0)
    logger.info("Watchlist candidates: %d | Entry candidates: %d", len(watch_results), len(entry_results))
    logger.info("Dual-mode scan total elapsed %.2fs", time.perf_counter() - scan_started_at)
    # Build profiling summary
    profile = {
        "history_download_time": float(history_download_time),
        "evaluation_time": float(eval_time),
    }
    try:
        if per_ticker_times:
            import statistics

            profile["per_ticker_count"] = len(per_ticker_times)
            profile["per_ticker_mean"] = float(statistics.mean(per_ticker_times))
            profile["per_ticker_median"] = float(statistics.median(per_ticker_times))
            profile["per_ticker_min"] = float(min(per_ticker_times))
            profile["per_ticker_max"] = float(max(per_ticker_times))
        else:
            profile["per_ticker_count"] = 0
    except Exception:
        pass

    # attach persist timings if available
    try:
        profile["persist_diag_time"] = float(persist_diag_time)
    except Exception:
        profile["persist_diag_time"] = 0.0
    try:
        profile["persist_setup_time"] = float(persist_setup_time)
    except Exception:
        profile["persist_setup_time"] = 0.0
    try:
        profile["persist_transition_time"] = float(persist_transition_time)
    except Exception:
        profile["persist_transition_time"] = 0.0
    try:
        profile["persist_trigger_time"] = float(persist_trigger_time)
    except Exception:
        profile["persist_trigger_time"] = 0.0

    if diagnostics_summary:
        return {"watchlist": watch_results, "entry": entry_results, "diagnostics": diagnostics_summary, "profile": profile}
    return {"watchlist": watch_results, "entry": entry_results, "profile": profile}

def run_scanner(config: Optional[ScannerConfig] = None, output_path: Optional[str] = None) -> pd.DataFrame:
    """Compatibility wrapper returning the actionable entry results DataFrame."""
    results = run_dual_mode_scan(config=config, output_path=output_path)
    return results.get("entry", pd.DataFrame())


def run_from_cli() -> None:
    """CLI entrypoint for running the scanner from the terminal."""
    results = run_scanner()
    print(format_results(results))
