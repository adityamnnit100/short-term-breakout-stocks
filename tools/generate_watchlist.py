"""Generate a top-N watchlist of Pre-Breakout setups.
Filters: `Setup_Score >= 7`, `Signal_Strength >= 7`, `RS_Rating >= 80` (configurable).
Saves CSVs: `tools/watchlist_nifty.csv` and `tools/watchlist_total.csv`.
"""
import sys
sys.path.insert(0, '/home/kumar/Downloads/workspace/stocks')
import breakout
import pandas as pd
import json

TOP_N = 50
RS_FLOOR = 80.0
SETUP_MIN = 7.0
STRENGTH_MIN = 7.0


def make_watchlist(universe: str):
    print(f"Running Pre-Breakout scan for {universe}...")
    # Conservative Pre-Breakout presets
    vol_thresh = 0.6
    rsi_min, rsi_max = 35, 70
    dist_thresh = 5.0

    results, stats = breakout.run_scanner(
        vol_thresh=vol_thresh,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        dist_thresh=dist_thresh,
        scanner_type='Pre-Breakout',
        universe=universe,
        timeframe='1d',
    )

    if results is None or results.empty:
        print('No results from scanner')
        return None

    df = results.copy()
    # Ensure numeric types
    for c in ['Setup_Score', 'Signal_Strength', 'RS_Rating']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # Apply filters
    filtered = df[
        (df.get('Setup_Score', 0) >= SETUP_MIN) &
        (df.get('Signal_Strength', 0) >= STRENGTH_MIN) &
        (df.get('RS_Rating', 0) >= RS_FLOOR)
    ]

    if filtered.empty:
        print('No candidates match filter criteria')
        return df

    # Sort by Signal_Strength then Setup_Score then RVOL
    filtered = filtered.sort_values(['Signal_Strength', 'Setup_Score', 'RVOL'], ascending=[False, False, False])
    top = filtered.head(TOP_N)

    out_file = f'tools/watchlist_{"total" if universe.startswith("Total") else "nifty"}.csv'
    top.to_csv(out_file, index=False)
    print(f'Saved top {len(top)} to {out_file}')
    print('Top tickers:')
    print(top[['Ticker','RS_Rating','Setup_Score','Signal_Strength','RVOL','Pattern','Action']].to_string(index=False))
    return top


if __name__ == '__main__':
    # Run for both universes sequentially
    for u in ['Nifty 500', 'Total Market (Cap Focused)']:
        try:
            make_watchlist(u)
        except Exception as e:
            print('Scan failed for', u, str(e))
