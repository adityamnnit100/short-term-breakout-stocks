# Small smoke-run script for Pre-Breakout scanner
import json
import traceback
import breakout
import scanner_service
from alphascanner_ui.data import get_sector_mapping

# Force a small universe to keep runtime short
breakout.get_nifty_500 = lambda: [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS", "HDFCBANK.NS"
]

def main():
    try:
        sector_map = get_sector_mapping("Nifty 500")
        results, stats, scan_time = scanner_service.perform_fresh_scan(
            universe="Nifty 500",
            vol_thresh=0.6,
            rsi_min=35,
            rsi_max=70,
            dist_thresh=5.0,
            min_mkt_cap_cr=0,
            max_mkt_cap_cr=0,
            scanner_type="Pre-Breakout",
            timeframe="1d",
            sector_map=sector_map,
            include_news_sentiment=False,
            progress_callback=None,
            force_fresh=True,
        )

        print("SCAN_TIME:", scan_time)
        print("STATS:")
        print(json.dumps(stats, indent=2))
        if results is None or results.empty:
            print("RESULTS: <empty>")
        else:
            # print top 10 rows as JSON
            print("TOP_HITS:")
            print(results.head(10).to_json(orient='records'))
    except Exception:
        traceback.print_exc()

if __name__ == '__main__':
    main()
