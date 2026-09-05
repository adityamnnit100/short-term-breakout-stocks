"""Micro-benchmark for cache vs fresh scan.

Run from the repository root with PYTHONPATH set to trading_env site-packages
if needed. This script runs `perform_fresh_scan` twice (fresh and cached) and
prints elapsed times for comparison.
"""
from __future__ import annotations

import time
import pprint

from scanner_service import perform_fresh_scan


def run_benchmark(fast_scan: bool = True):
    params = dict(
        universe='Nifty 500',
        vol_thresh=1.0,
        rsi_min=35,
        rsi_max=75,
        dist_thresh=5.0,
        min_mkt_cap_cr=0,
        max_mkt_cap_cr=0,
        scanner_type='Modular Momentum',
        scan_mode='Entry Scanner',
        timeframe='1d',
        force_fresh=False,
        fast_scan=fast_scan,
    )

    print('Running fresh scan (use_cache=False)')
    t0 = time.perf_counter()
    _, stats_fresh, _ = perform_fresh_scan(**{**params, 'use_cache': False})
    t1 = time.perf_counter()

    print('Running cached scan (use_cache=True)')
    t2 = time.perf_counter()
    _, stats_cached, _ = perform_fresh_scan(**{**params, 'use_cache': True})
    t3 = time.perf_counter()

    print('\nResults:')
    print('Fresh elapsed:', t1 - t0)
    print('Cached elapsed:', t3 - t2)
    print('\nFresh stats:')
    pprint.pprint(stats_fresh)
    print('\nCached stats:')
    pprint.pprint(stats_cached)


if __name__ == '__main__':
    run_benchmark()
