"""scanner_service.py – thin service layer between dashboard and breakout engine."""

import datetime
from breakout import run_scanner, get_cached_results, save_results_to_db


def fetch_cached_data(use_cache: bool):
    """Return (results_df, stats_dict, scan_time_str) from DB cache, or (None, None, None)."""
    if not use_cache:
        return None, None, None
    return get_cached_results()


def perform_fresh_scan(universe, vol_thresh, rsi_range, dist_thresh, mkt_cap_min, sector_map, progress_callback=None):
    """Run a live scan, persist results, and return (results_df, stats_dict, scan_time_str)."""
    results, stats = run_scanner(
        vol_thresh=vol_thresh,
        rsi_min=rsi_range[0],
        rsi_max=rsi_range[1],
        dist_thresh=dist_thresh,
        min_mkt_cap_cr=mkt_cap_min,
        universe=universe,
        sector_map=sector_map,
        progress_callback=progress_callback,
    )

    scan_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if results is not None and not results.empty:
        save_results_to_db(results, stats)

    return results, stats, scan_time