"""scanner_service.py – thin service layer between dashboard and breakout engine."""

from datetime import datetime
from breakout import run_scanner, get_cached_results, save_results_to_db, is_market_open, get_last_market_close_utc


def fetch_cached_data(use_cache: bool, universe: str = None):
    """Return (results_df, stats_dict, scan_time_str) from DB cache, or (None, None, None)."""
    if not use_cache:
        return None, None, None
    return get_cached_results(universe=universe)


def perform_fresh_scan(universe, vol_thresh, rsi_min, rsi_max, dist_thresh, min_mkt_cap_cr, max_mkt_cap_cr, scanner_type, sector_map, progress_callback=None, force_fresh=True):
    """Run a live scan, persist results, and return (results_df, stats_dict, scan_time_str)."""
    
    # PERFORMANCE OPTIMIZATION:
    # If market is closed, check if we already have a scan generated after the last market close.
    if not is_market_open() and not force_fresh:
        cached_df, cached_stats, cached_time_str = get_cached_results(hours=24, universe=universe)
        if cached_df is not None and cached_time_str:
            try:
                # cached_time_str from SQLite is UTC
                cache_time = datetime.strptime(cached_time_str, "%Y-%m-%d %H:%M:%S")
                last_close_utc = get_last_market_close_utc()
                if cache_time >= last_close_utc:
                    return cached_df, cached_stats, cached_time_str
            except Exception:
                pass 

    # Proceed with live scan if market is open or no valid post-market cache found
    results, stats = run_scanner(
        vol_thresh=vol_thresh,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        dist_thresh=dist_thresh,
        min_mkt_cap_cr=min_mkt_cap_cr,
        max_mkt_cap_cr=max_mkt_cap_cr,
        universe=universe,
        scanner_type=scanner_type,
        sector_map=sector_map,
        progress_callback=progress_callback,
    )

    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if results is not None and not results.empty:
        save_results_to_db(results, stats)

    return results, stats, scan_time
