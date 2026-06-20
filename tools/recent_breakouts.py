"""Scan recent breakout events (past 30 trading days) across Nifty 500.

For each ticker, find dates in the past 30 trading days where price closed
above the prior 20-day high (breakout). For each breakout, compute returns
after 1,3,5,10 trading days and capture technicals (RSI, RVOL, OBV/MFI,
squeeze, volume surge, base weeks).

Outputs a JSON summary to stdout and a CSV to ./tools/recent_breakouts.csv
"""
import sys
import json
from datetime import datetime, timedelta
import traceback

sys.path.insert(0, '/home/kumar/Downloads/workspace/stocks')
import yfinance as yf
import pandas as pd
import numpy as np
import breakout

OUT_CSV = 'tools/recent_breakouts.csv'

def analyze():
    tickers = breakout.get_nifty_500()
    # Fetch 3 months of data to cover 30 trading days
    period = '3mo'
    interval = '1d'

    print('Downloading data for', len(tickers), 'tickers...')
    data = yf.download(tickers, period=period, interval=interval, progress=False, threads=False, timeout=120)
    if isinstance(data.columns, pd.MultiIndex):
        data = data.loc[:, ~data.columns.duplicated()]

    all_close = data['Close'] if 'Close' in data else data

    results = []
    quality = breakout._scanner_quality_profile('Pre-Breakout', 'Nifty 500')
    breakout_buffer = 1 + quality['breakout_buffer_pct']/100.0

    # iterate tickers
    avail = all_close.columns.tolist() if isinstance(all_close, pd.DataFrame) else tickers

    for ticker in avail:
        try:
            df = breakout._extract_ticker(data, ticker)
            df = df.dropna(subset=['Close','High','Low','Open','Volume'])
            if df.empty or len(df) < 40:
                continue

            close = df['Close']
            high = df['High']
            low = df['Low']
            vol = df['Volume']

            # rolling detect for last 30 trading days
            end_idx = len(df) - 1
            start_scan_idx = max(20, end_idx - 60)  # scan last ~60 days for safety
            for j in range(start_scan_idx, end_idx + 1):
                sub = df.iloc[: j+1]
                if len(sub) < 21:
                    continue
                # prior 20-day high excluding current
                prev_h20 = float(sub['High'].iloc[-21:-1].max())
                ltp = float(sub['Close'].iloc[-1])
                date = sub.index[-1]
                days_ago = (df.index[-1] - date).days
                # consider only breakouts within last 30 calendar days
                if (df.index[-1] - date).days > 30:
                    continue

                broke_20d = ltp >= prev_h20 * breakout_buffer
                if not broke_20d:
                    continue

                # compute future returns 1,3,5,10 trading days ahead
                def future_return(idx, days):
                    target = idx + days
                    if target < len(df):
                        return (float(df['Close'].iloc[target]) / float(df['Close'].iloc[idx]) - 1.0) * 100.0
                    return None

                idx = sub.index.get_loc(date)
                r1 = future_return(idx, 1)
                r3 = future_return(idx, 3)
                r5 = future_return(idx, 5)
                r10 = future_return(idx, 10)

                # technicals at breakout
                rsi = float(breakout.calculate_rsi(close).iloc[j]) if j < len(close) else None
                rvol = breakout.calculate_rvol(vol.iloc[: j+1])
                is_squeeze = breakout.detect_bb_kc_squeeze(close.iloc[: j+1], high.iloc[: j+1], low.iloc[: j+1])
                is_tight = breakout.detect_vcp_tightness(close.iloc[: j+1])
                is_nr7 = breakout.detect_nr7(sub)
                base_weeks = breakout.calculate_base_weeks(sub)
                vol_surge = breakout.detect_volume_surge(vol.iloc[: j+1])

                # OBV/MFI
                try:
                    obv = breakout.calculate_obv(close.iloc[: j+1], vol.iloc[: j+1])
                    obv_up = bool(obv.iloc[-1] > obv.iloc[-6]) if len(obv) >= 6 else False
                except Exception:
                    obv_up = False
                try:
                    mfi = breakout.calculate_mfi(high.iloc[: j+1], low.iloc[: j+1], close.iloc[: j+1], vol.iloc[: j+1])
                    mfi_val = float(mfi.iloc[-1])
                except Exception:
                    mfi_val = None

                results.append({
                    'Ticker': ticker,
                    'Date': str(pd.Timestamp(date).date()),
                    'Close': ltp,
                    'Prev20High': prev_h20,
                    'R1': r1, 'R3': r3, 'R5': r5, 'R10': r10,
                    'RSI': rsi, 'RVOL': round(rvol,2), 'OBV_Up': obv_up, 'MFI': mfi_val,
                    'Squeeze': is_squeeze, 'Tight': is_tight, 'NR7': is_nr7, 'BaseWeeks': base_weeks, 'VolSurge': vol_surge
                })
        except Exception as e:
            # continue on errors
            #print('Error', ticker, e)
            continue

    df_out = pd.DataFrame(results)
    if not df_out.empty:
        df_out.to_csv(OUT_CSV, index=False)
    print('Found', len(df_out), 'breakout events in last 30 days. Saved to', OUT_CSV)
    print(df_out.sort_values('R5', ascending=False).head(30).to_json(orient='records'))

if __name__ == '__main__':
    try:
        analyze()
    except Exception:
        traceback.print_exc()
