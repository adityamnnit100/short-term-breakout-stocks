# Run Breakout scan (originally Breakout) with the new strict volume confirmation and report hit counts for both universes
import sys, json
sys.path.insert(0, '/home/kumar/Downloads/workspace/stocks')
from alphascanner_ui.data import get_sector_mapping
import scanner_service


def run_scan(universe):
    sector_map = get_sector_mapping(universe if universe=='Nifty 500' else 'Nifty 500')
    results, stats, scan_time = scanner_service.perform_fresh_scan(
        universe=universe,
        vol_thresh=1.0,
        rsi_min=50,
        rsi_max=85,
        dist_thresh=1.5,
        min_mkt_cap_cr=0,
        max_mkt_cap_cr=0,
        scanner_type='Breakout',
        timeframe='1d',
        sector_map=sector_map,
        include_news_sentiment=False,
        progress_callback=None,
        force_fresh=True,
    )
    count = 0 if results is None else len(results)
    print(f"{universe} -> hits: {count}")
    return results, stats

if __name__ == '__main__':
    run_scan('Nifty 500')
    run_scan('Total Market (Cap Focused)')
