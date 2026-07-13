"""Compatibility layer between the dashboard and the new modular scanner."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from pathlib import Path

import pandas as pd

from scanner.config import ScannerConfig
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
):
    """Run the modular scanner and return dashboard-compatible output."""
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
    if scanner_type == "Modular Momentum":
        config = ScannerConfig()
        config.universe = universe or config.universe
        config.interval = _normalize_interval(timeframe or config.interval)
        logger.debug("Routing to modular scanner with config=%s", config.as_dict())

        if progress_callback:
            progress_callback(0.15)

        dual_results = run_dual_mode_scan(config=config, progress_callback=progress_callback, use_cache=use_cache)
        results = dual_results.get("watchlist" if scan_mode == "Watchlist Scanner" else "entry", pd.DataFrame())
        diagnostics = dual_results.get("diagnostics")

        if progress_callback:
            progress_callback(1.0)

        if results is None or results.empty:
            stats = _build_basic_stats(pd.DataFrame(), config.universe, timeframe, scan_mode)
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
    return results, stats, scan_time


def _build_basic_stats(results: pd.DataFrame, universe: str, timeframe: str, scan_mode: str) -> dict:
    return {
        "scanned": len(results),
        "universe_size": len(results),
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
