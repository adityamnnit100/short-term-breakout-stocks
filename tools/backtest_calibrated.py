"""Calibrated backtest for high-quality candidates:
Filter: RS >= 80 AND (VCP tight OR BaseWeeks >= 3 OR VolSurge == True)
Compare baseline vs strict volume-confirmed breakouts over 12 months.
"""
import sys, traceback, json
from datetime import datetime
sys.path.insert(0, '/home/kumar/Downloads/workspace/stocks')
import yfinance as yf
import pandas as pd
import numpy as np
import breakout

PERIOD = '12mo'
HORIZONS = [1,3,5,10]
OUT_CSV = 'tools/backtest_calibrated.csv'


def analyze(universe_label):
    tickers = breakout.get_nifty_total_market() if universe_label.startswith('Total') else breakout.get_nifty_500()
    print(f'Downloading {len(tickers)} tickers + benchmark for {universe_label}...')
    data = yf.download(tickers, period=PERIOD, interval='1d', progress=False, threads=False, timeout=300)
    nifty = yf.download('^NSEI', period=PERIOD, interval='1d', progress=False, threads=False, timeout=120)
    if isinstance(data.columns, pd.MultiIndex):
        data = data.loc[:, ~data.columns.duplicated()]

    nifty_close = None
    try:
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty_close = nifty['Close'].dropna()
    except Exception:
        nifty_close = None

    results = []
    quality = breakout._scanner_quality_profile('Breakout', universe_label)
    breakout_buffer = 1 + quality['breakout_buffer_pct']/100.0

    avail = data.columns.get_level_values(1).unique().tolist() if isinstance(data.columns, pd.MultiIndex) else tickers

    for ticker in avail:
        try:
            df = breakout._extract_ticker(data, ticker)
            df = df.dropna(subset=['Close','High','Low','Open','Volume'])
            if df.empty or len(df) < 60:
                continue

            close = df['Close']; high = df['High']; low = df['Low']; vol = df['Volume']
            # RS vs nifty
            try:
                rs_rating = breakout.calculate_relative_strength(close, nifty_close)
            except Exception:
                rs_rating = 0.0

            rsi_series = breakout.calculate_rsi(close)
            obv_series = breakout.calculate_obv(close, vol)
            mfi_series = breakout.calculate_mfi(high, low, close, vol)

            for idx in range(21, len(df)-1):
                date = df.index[idx]
                ltp = float(close.iloc[idx])
                prev_h20 = float(df['High'].iloc[idx-20:idx].max())
                if ltp < prev_h20 * breakout_buffer:
                    continue

                rvol = breakout.calculate_rvol(vol.iloc[: idx+1])
                is_surge = breakout.detect_volume_surge(vol.iloc[: idx+1])
                is_tight = breakout.detect_vcp_tightness(close.iloc[: idx+1])
                base_weeks = breakout.calculate_base_weeks(df.iloc[: idx+1])

                # high-quality filter
                rs_val = rs_rating if isinstance(rs_rating, (int, float)) else float(rs_rating)
                if rs_val < 80 and not (is_tight or base_weeks >= 3 or is_surge):
                    continue

                # forward returns
                returns = {}
                for h in HORIZONS:
                    t = idx + h
                    if t < len(df):
                        returns[f'R{h}'] = (float(close.iloc[t]) / float(close.iloc[idx]) - 1.0) * 100.0
                    else:
                        returns[f'R{h}'] = None

                obv_up = False
                if len(obv_series) >= 6:
                    try:
                        obv_up = bool(obv_series.iloc[idx] > obv_series.iloc[idx-6])
                    except Exception:
                        obv_up = False
                try:
                    mfi_val = float(mfi_series.iloc[idx])
                except Exception:
                    mfi_val = None

                event = {
                    'Ticker': ticker,
                    'Date': str(pd.Timestamp(date).date()),
                    'RS': round(rs_val,1),
                    'Close': ltp,
                    'Prev20High': prev_h20,
                    'RVOL': round(rvol,2),
                    'OBV_Up': bool(obv_up),
                    'MFI': mfi_val,
                    'VolSurge': bool(is_surge),
                    'Tight': bool(is_tight),
                    'BaseWeeks': int(base_weeks)
                }
                for k,v in returns.items(): event[k]=v
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

    fname = OUT_CSV.replace('.csv', f'_{"total" if universe_label.startswith("Total") else "nifty"}.csv')
    df_out.to_csv(fname, index=False)

    summary = {}
    for label,subset in [('All', df_out), ('Strict', df_out[df_out['StrictConfirm']])]:
        row = {'events': len(subset)}
        for h in HORIZONS:
            col = f'R{h}'
            valid = subset[col].dropna()
            wins = (valid>0).sum()
            mean = valid.mean() if len(valid)>0 else None
            median = valid.median() if len(valid)>0 else None
            winrate = wins/len(valid) if len(valid)>0 else None
            row[col] = {'count': len(valid), 'win': int(wins), 'winrate': round(winrate,4) if winrate is not None else None, 'mean': round(mean,3) if mean is not None else None, 'median': round(median,3) if median is not None else None}
        summary[label]=row

    return df_out, summary


if __name__ == '__main__':
    try:
        out_n, s_n = analyze('Nifty 500')
        out_t, s_t = analyze('Total Market (Cap Focused)')
        print('\n== Nifty 500 Calibrated Summary ==')
        print(json.dumps(s_n, indent=2))
        print('\n== Total Market Calibrated Summary ==')
        print(json.dumps(s_t, indent=2))
    except Exception:
        traceback.print_exc()
"""Calibrated backtest: compare baseline vs strict volume confirmation for high-quality candidates.
High-quality definition: RS_Rating >= 80 AND (VCP tight OR BaseWeeks >= 3 OR VolSurge).
Evaluated over past 12 months for Nifty 500 and Total Market.
"""
import sys, traceback, json
sys.path.insert(0, '/home/kumar/Downloads/workspace/stocks')
from datetime import datetime
import yfinance as yf
import pandas as pd
import numpy as np
import breakout

HORIZONS = [1,3,5,10]
PERIOD = '12mo'
OUT_PREFIX = 'tools/backtest_calibrated'


def analyze(universe_label):
    tickers = breakout.get_nifty_total_market() if universe_label.startswith('Total') else breakout.get_nifty_500()
    print(f'Downloading {len(tickers)} tickers for {universe_label}...')
    data = yf.download(tickers, period=PERIOD, interval='1d', progress=False, threads=False, timeout=300)
    if isinstance(data.columns, pd.MultiIndex):
        data = data.loc[:, ~data.columns.duplicated()]

    # benchmark for RS calculation
    try:
        nifty = yf.download('^NSEI', period=PERIOD, interval='1d', progress=False, threads=False, timeout=120)
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty_close = nifty['Close']
    except Exception:
        nifty_close = None

    results = []

    quality = breakout._scanner_quality_profile('Breakout', universe_label)
    breakout_buffer = 1 + quality['breakout_buffer_pct']/100.0

    avail = data['Close'].columns.tolist() if isinstance(data['Close'], pd.DataFrame) else tickers

    for ticker in avail:
        try:
            df = breakout._extract_ticker(data, ticker)
            df = df.dropna(subset=['Close','High','Low','Open','Volume'])
            if df.empty or len(df) < 60:
                continue

            close = df['Close']; high = df['High']; low = df['Low']; vol = df['Volume']
            # compute rs rating using available nifty_close aligned
            try:
                idx_close = nifty_close.reindex(close.index) if nifty_close is not None else None
                rs_rating = breakout.calculate_relative_strength(close, idx_close) if idx_close is not None else 0.0
            except Exception:
                rs_rating = 0.0

            rsi_series = breakout.calculate_rsi(close)
            obv_series = breakout.calculate_obv(close, vol)
            mfi_series = breakout.calculate_mfi(high, low, close, vol)

            for idx in range(21, len(df)-10):
                date = df.index[idx]
                ltp = float(close.iloc[idx])
                prev_h20 = float(df['High'].iloc[idx-20:idx].max())
                if ltp < prev_h20 * breakout_buffer:
                    continue

                # forward returns
                returns = {}
                for h in HORIZONS:
                    t = idx + h
                    if t < len(df):
                        returns[f'R{h}'] = (float(close.iloc[t]) / float(close.iloc[idx]) - 1.0) * 100.0
                    else:
                        returns[f'R{h}'] = None

                rvol = breakout.calculate_rvol(vol.iloc[: idx+1])
                is_surge = breakout.detect_volume_surge(vol.iloc[: idx+1])
                is_tight = breakout.detect_vcp_tightness(close.iloc[: idx+1])
                base_weeks = breakout.calculate_base_weeks(df.iloc[: idx+1])

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

                strict_confirm = (obv_up or (rvol >= 1.5)) and ((mfi_val is not None and mfi_val >= 60) or is_surge)
                high_quality = (rs_rating >= 80.0) and (is_tight or base_weeks >= 3 or is_surge)

                results.append({
                    'Ticker': ticker,
                    'Date': str(pd.Timestamp(date).date()),
                    'RS_Rating': round(rs_rating,1),
                    'Close': ltp,
                    'Prev20High': prev_h20,
                    'RVOL': round(rvol,2),
                    'OBV_Up': bool(obv_up),
                    'MFI': mfi_val,
                    'VolSurge': bool(is_surge),
                    'Tight': bool(is_tight),
                    'BaseWeeks': int(base_weeks),
                    'StrictConfirm': bool(strict_confirm),
                    'HighQuality': bool(high_quality),
                    **returns
                })
        except Exception:
            continue

    df_out = pd.DataFrame(results)
    if df_out.empty:
        print('No events for', universe_label)
        return None

    out_csv = OUT_PREFIX + ('_total.csv' if universe_label.startswith('Total') else '_nifty.csv')
    df_out.to_csv(out_csv, index=False)

    # Compute summaries for groups
    def summary_for(subset):
        row = {'events': len(subset)}
        for h in HORIZONS:
            col = f'R{h}'
            valid = subset[col].dropna()
            wins = (valid>0).sum()
            row[col] = {'count': len(valid), 'win': int(wins), 'winrate': round(wins/len(valid),4) if len(valid)>0 else None, 'mean': round(valid.mean(),3) if len(valid)>0 else None}
        return row

    groups = {
        'All': df_out,
        'Strict': df_out[df_out['StrictConfirm']],
        'HighQuality': df_out[df_out['HighQuality']],
        'HQ_Strict': df_out[(df_out['HighQuality']) & (df_out['StrictConfirm'])]
    }

    summary = {k: summary_for(v) for k,v in groups.items()}
    return df_out, summary

if __name__ == '__main__':
    try:
        out_n, s_n = analyze('Nifty 500')
        out_t, s_t = analyze('Total Market (Cap Focused)')
        print('\n== Nifty 500 Calibrated Summary ==')
        print(json.dumps(s_n, indent=2))
        print('\n== Total Market Calibrated Summary ==')
        print(json.dumps(s_t, indent=2))
    except Exception:
        traceback.print_exc()
