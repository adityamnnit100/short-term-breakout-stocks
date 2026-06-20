"""Backtest breakout conversion over past 12 months:
Compares baseline (any 20-day breakout) vs strict volume confirmation rule:
  (OBV rising OR RVOL>=1.5) AND (MFI>=60 OR VolSurge)
Outputs a summary JSON and CSV of events.
"""
import sys, json, traceback
from datetime import datetime
sys.path.insert(0, '/home/kumar/Downloads/workspace/stocks')
import yfinance as yf
import pandas as pd
import numpy as np
import breakout

OUT_CSV = 'tools/backtest_volume_confirmation.csv'

# horizons to evaluate (trading days)
HORIZONS = [1,3,5,10]
PERIOD = '12mo'


def analyze(universe_label):
    tickers = breakout.get_nifty_total_market() if universe_label.startswith('Total') else breakout.get_nifty_500()
    print(f'Downloading {len(tickers)} tickers for {universe_label}...')
    data = yf.download(tickers, period=PERIOD, interval='1d', progress=False, threads=False, timeout=300)
    if isinstance(data.columns, pd.MultiIndex):
        data = data.loc[:, ~data.columns.duplicated()]

    all_close = data['Close'] if 'Close' in data else data
    results = []

    quality = breakout._scanner_quality_profile('Breakout', universe_label)
    breakout_buffer = 1 + quality['breakout_buffer_pct']/100.0

    avail = all_close.columns.tolist() if isinstance(all_close, pd.DataFrame) else tickers

    for ticker in avail:
        try:
            df = breakout._extract_ticker(data, ticker)
            df = df.dropna(subset=['Close','High','Low','Open','Volume'])
            if df.empty or len(df) < 60:
                continue

            close = df['Close']; high = df['High']; low = df['Low']; vol = df['Volume']
            rsi_series = breakout.calculate_rsi(close)
            obv_series = breakout.calculate_obv(close, vol)
            mfi_series = breakout.calculate_mfi(high, low, close, vol)

            for idx in range(21, len(df)-1):
                date = df.index[idx]
                ltp = float(close.iloc[idx])
                prev_h20 = float(df['High'].iloc[idx-20:idx].max())
                if ltp < prev_h20 * breakout_buffer:
                    continue

                # compute forward returns
                returns = {}
                for h in HORIZONS:
                    t = idx + h
                    if t < len(df):
                        returns[f'R{h}'] = (float(close.iloc[t]) / float(close.iloc[idx]) - 1.0) * 100.0
                    else:
                        returns[f'R{h}'] = None

                # technicals at breakout
                rsi = float(rsi_series.iloc[idx]) if idx < len(rsi_series) else None
                rvol = breakout.calculate_rvol(vol.iloc[: idx+1])
                is_surge = breakout.detect_volume_surge(vol.iloc[: idx+1])
                is_tight = breakout.detect_vcp_tightness(close.iloc[: idx+1])

                obv_up = False
                if len(obv_series) >= 6:
                    try:
                        obv_up = bool(obv_series.iloc[idx] > obv_series.iloc[idx-6])
                    except Exception:
                        obv_up = False
                mfi_val = None
                try:
                    mfi_val = float(mfi_series.iloc[idx])
                except Exception:
                    mfi_val = None

                # baseline event (any breakout)
                event = {
                    'Ticker': ticker,
                    'Date': str(pd.Timestamp(date).date()),
                    'Close': ltp,
                    'Prev20High': prev_h20,
                    'RVOL': round(rvol,2),
                    'OBV_Up': bool(obv_up),
                    'MFI': mfi_val,
                    'VolSurge': bool(is_surge),
                    'Tight': bool(is_tight),
                    **returns
                }
                # strict confirmation
                vol_confirm = (obv_up or (rvol >= 1.5)) and ((mfi_val is not None and mfi_val >= 60) or is_surge)
                event['StrictConfirm'] = bool(vol_confirm)
                results.append(event)
        except Exception:
            continue

    df_out = pd.DataFrame(results)
    if df_out.empty:
        print('No events')
        return None

    df_out.to_csv(OUT_CSV.replace('.csv', f'_{"total" if universe_label.startswith("Total") else "nifty"}.csv'), index=False)

    summary = {}
    for label,subset in [('All', df_out), ('Strict', df_out[df_out['StrictConfirm']])]:
        row = {}
        row['events'] = len(subset)
        for h in HORIZONS:
            col = f'R{h}'
            valid = subset[col].dropna()
            wins = (valid>0).sum()
            losses = (valid<=0).sum()
            mean = valid.mean() if len(valid)>0 else None
            median = valid.median() if len(valid)>0 else None
            winrate = wins/len(valid) if len(valid)>0 else None
            row[col] = {'count': len(valid), 'win': int(wins), 'winrate': round(winrate,4) if winrate is not None else None, 'mean': round(mean,3) if mean is not None else None, 'median': round(median,3) if median is not None else None}
        summary[label] = row

    return df_out, summary

if __name__ == '__main__':
    try:
        out_n, s_n = analyze('Nifty 500')
        out_t, s_t = analyze('Total Market (Cap Focused)')
        print('\n== Nifty 500 Summary ==')
        print(json.dumps(s_n, indent=2))
        print('\n== Total Market Summary ==')
        print(json.dumps(s_t, indent=2))
    except Exception:
        traceback.print_exc()
