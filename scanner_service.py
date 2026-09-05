"""Compatibility layer between the dashboard and the new modular scanner."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from pathlib import Path
import time

import pandas as pd

from scanner.config import ScannerConfig
from scanner.data import get_universe
from scanner.scanner import run_dual_mode_scan
from utils.yf_cache import _normalize_interval

import logging

logger = logging.getLogger("AlphaScanner.Service")


def fetch_cached_data(use_cache: bool, universe: str = None, scanner_type: str = None, timeframe: str = "1d", scan_mode: str = None):
    """Return cached scan data when available; otherwise return None values."""
    logger.debug(
        "fetch_cached_data(use_cache=%s, universe=%s, scanner_type=%s, timeframe=%s, scan_mode=%s)",
        use_cache,
        universe,
        scanner_type,
        timeframe,
        scan_mode,
    )
    if not use_cache:
        return None, None, None

    if scanner_type == "Modular Momentum":
        return _fetch_modular_cached_data(universe=universe, scan_mode=scan_mode, timeframe=timeframe)

    return _fetch_legacy_cached_data(universe=universe, scanner_type=scanner_type, timeframe=timeframe)


def perform_fresh_scan(
    universe,
    vol_thresh,
    rsi_min,
    rsi_max,
    dist_thresh,
    min_mkt_cap_cr,
    max_mkt_cap_cr,
    scanner_type,
    scan_mode: str = "Entry Scanner",
    timeframe: str = "1d",
    sector_map=None,
    include_news_sentiment: bool = False,
    progress_callback=None,
    force_fresh=True,
    use_cache: bool = False,
    fast_scan: bool = False,
    short_term: bool = False,
):
    """Run the modular scanner and return dashboard-compatible output."""
    started_at = time.perf_counter()
    logger.debug(
        "perform_fresh_scan(scanner_type=%s, universe=%s, timeframe=%s, scan_mode=%s, use_cache=%s, vol_thresh=%s, rsi_min=%s, rsi_max=%s, dist_thresh=%s, min_mkt_cap_cr=%s, max_mkt_cap_cr=%s)",
        scanner_type,
        universe,
        timeframe,
        scan_mode,
        use_cache,
        vol_thresh,
        rsi_min,
        rsi_max,
        dist_thresh,
        min_mkt_cap_cr,
        max_mkt_cap_cr,
    )
    # Allow a dedicated short-term scanner type that maps to the modular
    # scanner but enables short-term presets and intraday gating.
    scanner_type_normalized = (scanner_type or "").strip().lower()
    if scanner_type_normalized in ("short term", "short-term", "short_term"):
        scanner_type = "Modular Momentum"
        short_term = True

    if scanner_type == "Modular Momentum":
        config = ScannerConfig()
        config.universe = universe or config.universe
        config.interval = _normalize_interval(timeframe or config.interval)
        config.quality_min_market_cap_cr = min_mkt_cap_cr or 0.0
        config.quality_max_market_cap_cr = max_mkt_cap_cr or 0.0
        logger.debug("Routing to modular scanner with config=%s", config.as_dict())

        # Map UI filters into ScannerConfig so the modular scanner respects user inputs.
        try:
            # Volume threshold in UI is expressed as ×avg. Apply it to trigger relative volume checks.
            v = float(vol_thresh or config.trigger_relative_volume_5d_min)
            # enforce reasonable bounds
            v = max(0.1, min(v, 10.0))
            config.trigger_relative_volume_5d_min = v
            # Make 10d/20d thresholds slightly more permissive based on 5d value.
            config.trigger_relative_volume_10d_min = float(max(config.trigger_relative_volume_10d_min, v * 0.9))
            config.trigger_relative_volume_20d_min = float(max(config.trigger_relative_volume_20d_min, v * 0.8))

            # Proximity to high (distance %) should influence setup distance limits.
            d = float(dist_thresh or config.setup_max_distance_to_high_pct)
            config.setup_max_distance_to_high_pct = max(0.1, min(d, 50.0))

            # Map RSI range to a conservative relative-strength requirement for quality and entry.
            # UI RSI is 0-100 scale; clamp and apply.
            rmin = int(max(0, min(int(rsi_min or config.quality_min_relative_strength), 100)))
            rmax = int(max(0, min(int(rsi_max or getattr(config, "trigger_rs_proxy_min", 0)), 100)))
            config.quality_min_relative_strength = float(rmin)
            # The trigger RS proxy is used as a relative ranking proxy; raise it toward the UI max but
            # avoid lowering configured defaults. Keep in same 0-100 scale.
            config.trigger_rs_proxy_min = float(max(getattr(config, "trigger_rs_proxy_min", 0.0), float(rmax)))
        except Exception:
            logger.debug("Failed to map UI filters into ScannerConfig; using defaults")

        # If a fast scan is requested, relax historical lookback and increase
        # parallelism to reduce total run time. This trades off depth for speed
        # and should be opt-in from the UI or CLI.
        if fast_scan:
            try:
                # shorter lookback reduces download and indicator work
                config.lookback_period = "6mo"
                # allow more parallel evaluation workers where CPU allows
                import os

                cpu = os.cpu_count() or 2
                config.scan_max_workers = max(4, min(64, cpu * 4))
                # increase downloader threads to overlap IO
                config.scan_download_threads = max(4, min(64, cpu * 8))
                # slightly larger download chunks to reduce roundtrips
                config.scan_download_chunk_size = max(25, int(config.scan_download_chunk_size * 2))
                # reduce min candles required so shorter histories still scan
                config.min_candles = max(80, int(config.min_candles / 3))
                # enable process pool for per-ticker evaluation to speed CPU-bound work
                config.scan_use_process_pool = True
                config.scan_process_workers = max(1, cpu)
            except Exception:
                pass

        # If a short-term preset is requested, apply a tuned configuration
        if short_term:
            try:
                # choose the preset based on the requested timeframe
                tf = (timeframe or config.interval or "").lower()
                if tf in ("5m", "15m", "1m"):
                    config.apply_preset("short_intraday")
                else:
                    config.apply_preset("short_hourly")
                # short-term scans are CPU/IO sensitive; enable process pool
                import os

                cpu = os.cpu_count() or 2
                config.scan_use_process_pool = True
                config.scan_process_workers = max(1, min(cpu, 4))
            except Exception:
                pass

        if progress_callback:
            progress_callback(0.15)

        scan_started_at = time.perf_counter()
        dual_results = run_dual_mode_scan(config=config, progress_callback=progress_callback, use_cache=use_cache)
        logger.info(
            "Modular scan finished in %.2fs for universe=%s interval=%s mode=%s",
            time.perf_counter() - scan_started_at,
            config.universe,
            config.interval,
            scan_mode,
        )
        results = dual_results.get("watchlist" if scan_mode == "Watchlist Scanner" else "entry", pd.DataFrame())
        diagnostics = dual_results.get("diagnostics")

        if progress_callback:
            progress_callback(1.0)

        if results is None or results.empty:
            stats = _build_basic_stats(pd.DataFrame(), config.universe, timeframe, scan_mode)
            stats["universe_size"] = len(get_universe(config)) if get_universe(config) is not None else 0
            if diagnostics:
                stats["diagnostics"] = diagnostics
                stats["diagnostics_summary_text"] = _format_diagnostics_summary(diagnostics)
            return pd.DataFrame(), stats, datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        stats = _build_basic_stats(results, config.universe, timeframe, scan_mode)
        if diagnostics:
            stats["diagnostics"] = diagnostics
            stats["diagnostics_summary_text"] = _format_diagnostics_summary(diagnostics)
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return results, stats, scan_time

    if progress_callback:
        progress_callback(0.10)

    try:
        import breakout
    except Exception as exc:
        stats = {"scanned": 0, "universe_size": 0, "universe": universe, "timeframe": timeframe, "error": str(exc)}
        return pd.DataFrame(), stats, datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if scanner_type == "FII Accumulation":
        logger.debug("Routing to legacy FII accumulation scanner")
        results, stats = breakout.run_fii_accumulation_scanner(
            min_mkt_cap_cr=min_mkt_cap_cr or 1000.0,
            min_fii_change_pct=max(vol_thresh or 1.0, 0.1),
        )
    else:
        timeframe = _normalize_interval(timeframe)
        logger.debug("Routing to legacy breakout scanner with normalized timeframe=%s", timeframe)
        scan_started_at = time.perf_counter()
        results, stats = breakout.run_scanner(
            vol_thresh=vol_thresh,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            dist_thresh=dist_thresh,
            min_mkt_cap_cr=min_mkt_cap_cr,
            max_mkt_cap_cr=max_mkt_cap_cr,
            scanner_type=scanner_type,
            universe=universe,
            timeframe=timeframe,
            sector_map=sector_map,
            include_news_sentiment=include_news_sentiment,
            progress_callback=progress_callback,
            incremental_fetch=force_fresh is False,
            use_cache=use_cache,
        )
        logger.info(
            "Legacy scan finished in %.2fs for universe=%s interval=%s scanner_type=%s",
            time.perf_counter() - scan_started_at,
            universe,
            timeframe,
            scanner_type,
        )

    if progress_callback:
        progress_callback(1.0)

    if results is None:
        results = pd.DataFrame()
    logger.debug(
        "perform_fresh_scan completed: rows=%s stats_keys=%s",
        len(results),
        sorted(stats.keys()) if isinstance(stats, dict) else type(stats).__name__,
    )
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(stats, dict):
        stats.setdefault("universe", universe)
        stats.setdefault("timeframe", timeframe)
    else:
        stats = {"scanned": len(results), "universe_size": len(results), "universe": universe, "timeframe": timeframe}
    logger.debug("perform_fresh_scan total elapsed=%.2fs", time.perf_counter() - started_at)
    return results, stats, scan_time


def _build_basic_stats(results: pd.DataFrame, universe: str, timeframe: str, scan_mode: str) -> dict:
    universe_size = len(results)
    if not results.empty and hasattr(results, "__len__"):
        universe_size = len(results)
    return {
        "scanned": len(results),
        "universe_size": universe_size,
        "universe": universe,
        "timeframe": timeframe,
        "scan_mode": scan_mode,
        "market_bias": "Neutral",
        "market_health": "Constructive",
        "trending_sectors": [],
        "sector_sentiment": {},
    }


def _format_diagnostics_summary(diagnostics: dict) -> str:
    if not diagnostics:
        return ""

    stages = diagnostics.get("stages", {})
    decisions = diagnostics.get("decisions", {})
    top_rules = diagnostics.get("most_restrictive_rules", [])
    lines = [
        f"Universe {diagnostics.get('universe', 0)}",
        f"Quality Filter: Passed {stages.get('quality', {}).get('passed', 0)} Rejected {stages.get('quality', {}).get('rejected', 0)}",
        f"Setup Engine: Passed {stages.get('setup', {}).get('passed', 0)} Rejected {stages.get('setup', {}).get('rejected', 0)}",
        f"Transition Engine: Passed {stages.get('transition', {}).get('passed', 0)} Rejected {stages.get('transition', {}).get('rejected', 0)}",
        f"BUY NOW {decisions.get('BUY NOW', 0)} | EARLY BUY {decisions.get('EARLY BUY', 0)} | WATCH {decisions.get('WATCH', 0)} | WAIT {decisions.get('WAIT', 0)}",
    ]
    if top_rules:
        lines.append("Most Restrictive Rules:")
        for idx, item in enumerate(top_rules, start=1):
            lines.append(f"{idx}. {item.get('rule')} rejected {item.get('rejected', 0)} stocks")
    return "\n".join(lines)


def _fetch_modular_cached_data(universe: str = None, scan_mode: str = None, timeframe: str = "1d"):
    """Load modular scan results from the local CSV exports when available."""
    scan_mode = scan_mode or "Entry Scanner"
    path = Path("data/watchlist.csv" if scan_mode == "Watchlist Scanner" else "data/entry.csv")
    if not path.exists():
        return None, None, None

    cache_age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    if cache_age > timedelta(hours=12):
        return None, None, None

    try:
        results = pd.read_csv(path)
    except Exception:
        return None, None, None

    if results.empty:
        return None, None, None

    stats = _build_basic_stats(results, universe or "Nifty 500", timeframe, scan_mode)
    scan_time = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return results, stats, scan_time


def _fetch_legacy_cached_data(universe: str = None, scanner_type: str = None, timeframe: str = "1d"):
    """Load legacy breakout scan results from the breakout cache if present."""
    try:
        import breakout
    except Exception:
        return None, None, None

    try:
        results, stats, scan_time = breakout.get_cached_results(
            hours=12,
            universe=universe,
            scanner_type=scanner_type,
            timeframe=timeframe,
        )
    except Exception:
        return None, None, None

    if results is None or results.empty:
        return None, None, None
    return results, stats, scan_time
