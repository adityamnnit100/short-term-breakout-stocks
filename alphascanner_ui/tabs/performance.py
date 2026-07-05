"""Performance tab: watchlist, quick-backtest, and per-ticker details."""
from typing import Optional

import pandas as pd
import streamlit as st

import breakout
from alphascanner_ui.charts import build_chart


def _run_scan(universe: str, vol_thresh: float, rsi_min: int, rsi_max: int, dist_thresh: float):
    with st.spinner('Running scanner...'):
        results, stats = breakout.run_scanner(
            vol_thresh=vol_thresh,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            dist_thresh=dist_thresh,
            scanner_type='Pre-Breakout',
            universe=universe,
            incremental_fetch=True,
    )
    return results, stats


def _score_column(df: pd.DataFrame) -> str:
    for column in ("Signal_Strength", "Setup_Score", "Entry Score", "Watchlist Score", "Total Score"):
        if column in df.columns:
            return column
    return ""


def _safe_display_columns(df: pd.DataFrame):
    preferred = ["Ticker", "RS_Rating", "Setup_Score", "Signal_Strength", "Entry Score", "Watchlist Score", "RVOL", "Vol_x", "Pattern", "Action", "Trade Quality", "Recommendation"]
    return [column for column in preferred if column in df.columns]


def _summarize_backtest(df: pd.DataFrame):
    # Lightweight summary using any forward return columns if present
    horizons = [c for c in df.columns if c.startswith('R')]
    summary = {}
    for h in horizons:
        vals = pd.to_numeric(df[h], errors='coerce').dropna()
        summary[h] = {'count': int(len(vals)), 'winrate': float((vals>0).sum() / len(vals)) if len(vals)>0 else None, 'mean': float(vals.mean()) if len(vals)>0 else None}
    return summary


def render():
    st.title('Performance')
    st.markdown('Lightweight watchlist, quick-backtest, and per-ticker details for Pre-Breakout setups.')

    col1, col2 = st.columns([2, 1])
    with col1:
        universe = st.selectbox('Universe', ['Nifty 500', 'Total Market (Cap Focused)'], index=0)
        vol_thresh = st.slider('RVOL threshold', 0.5, 3.0, 1.5, 0.1)
        rsi_min = st.slider('Min RSI', 30, 80, 40)
        rsi_max = st.slider('Max RSI', 60, 95, 75)
        dist_thresh = st.slider('Dist from high (%)', 0.5, 10.0, 3.0, 0.1)

    with col2:
        st.write('Quick actions')
        run_scan = st.button('Run Pre-Breakout Scan')
        run_quick_bt = st.button('Quick Calibrated Backtest')

    results = None
    stats = None
    if run_scan:
        results, stats = _run_scan(universe, vol_thresh, rsi_min, rsi_max, dist_thresh)

    if results is not None and not results.empty:
        st.subheader('Watchlist')
        score_col = _score_column(results)
        if not score_col:
            st.warning("The scan returned results, but none of the expected score columns were found.")
            return

        # Filters
        if score_col == "Setup_Score":
            min_setup = st.slider('Min Setup_Score', 0.0, 10.0, 7.0, 0.1)
            min_strength = st.slider('Min Signal_Strength', 0.0, 10.0, 7.0, 0.1)
        else:
            min_setup = st.slider(f'Min {score_col}', 0.0, 100.0, 0.0, 1.0)
            min_strength = 0.0

        df = results.copy()
        for c in ['Setup_Score', 'Signal_Strength', 'RS_Rating', 'Entry Score', 'Watchlist Score', 'Total Score']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')

        if score_col == "Setup_Score":
            filtered = df[(df.get('Setup_Score', 0) >= min_setup) & (df.get('Signal_Strength', 0) >= min_strength)]
        else:
            filtered = df[df.get(score_col, 0) >= min_setup]

        st.write(f'{len(filtered)} setups match filters')
        display_cols = _safe_display_columns(filtered)
        if display_cols:
            st.dataframe(filtered[display_cols].reset_index(drop=True))
        else:
            st.dataframe(filtered.reset_index(drop=True))

        if st.button('Export Watchlist CSV'):
            fn = f'tools/watchlist_{"total" if universe.startswith("Total") else "nifty"}.csv'
            filtered.to_csv(fn, index=False)
            st.success(f'Wrote {fn}')

        # Per-ticker detail: show chart for selected
        if 'Ticker' in filtered.columns and not filtered.empty:
            sel = st.selectbox('Select ticker for detail', options=filtered['Ticker'].astype(str).tolist())
        else:
            sel = None

        if sel:
            with st.spinner('Loading chart...'):
                df_t = breakout.fetch_history(sel, period='1y') if hasattr(breakout, 'fetch_history') else None
                if df_t is not None and not df_t.empty:
                    fig = build_chart(df_t, title=f'{sel} — 1y')
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info('No history available for chart')

    elif run_scan:
        st.info('No setups found for current filters.')

    if run_quick_bt:
        with st.spinner('Running calibrated backtest (this may take a few minutes)...'):
            try:
                from tools.backtest_calibrated import analyze as bt_analyze
                _, summary = bt_analyze(universe)
                st.subheader('Quick Backtest Summary')
                st.json(summary)
            except Exception as e:
                st.error(f'Backtest failed: {e}')
