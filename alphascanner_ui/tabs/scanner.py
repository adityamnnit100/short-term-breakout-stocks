"""Scanner tab UI."""

from typing import Optional

import pandas as pd
import streamlit as st

import scanner_service
from alphascanner_ui.charts import build_chart, render_top_picks, style_scanner_results
from alphascanner_ui.data import get_sector_mapping


def _apply_result_filters(results: pd.DataFrame) -> pd.DataFrame:
    with st.expander("Refine Visible Results", expanded=False):
        st.caption("These controls only narrow the current scan output. They do not rerun the scanner.")
        filter_col_1, filter_col_2, filter_col_3 = st.columns(3)
        min_strength = filter_col_1.slider("Min Strength", 0, 10, 1) # Default 1 for visibility
        min_rsi = filter_col_2.slider("Min RSI", 0, 100, 40) # Default 40
        min_vol = filter_col_3.slider("Min Volume ×", 1.0, 5.0, 1.0) # Default 1.0

    if results is None or results.empty:
        return results

    required_cols = ["Signal_Strength", "RSI", "Vol_x"]
    if not all(col in results.columns for col in required_cols):
        return results

    return results[
        (results["Signal_Strength"] >= min_strength)
        & (results["RSI"] >= min_rsi)
        & (results["Vol_x"] >= min_vol)
    ]


def _render_status_banner(
    results: Optional[pd.DataFrame],
    filtered_results: Optional[pd.DataFrame],
    scan_time: Optional[str],
    scan_source: Optional[str],
    stats: Optional[dict] = None,
) -> None:
    total_results = 0 if results is None else len(results)
    filtered_count = 0 if filtered_results is None else len(filtered_results)
    source_label = scan_source or "None"
    time_label = scan_time or "Never"
    
    trending = (stats or {}).get("trending_sectors", [])
    sector_scores = (stats or {}).get("sector_sentiment", {})
    
    pills = ""
    for s in trending:
        score = sector_scores.get(s, 5.0)
        color = "#00ffaa" if score >= 8 else ("#ffca28" if score >= 5 else "#ff5252")
        pills += f'<span class="mini-tag" style="background:rgba(0,0,0,0.3); color:{color}; border:1px solid {color}66; margin-top:4px; display:inline-block;">{s} ({score})</span>'

    sector_section = f'<div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.05);"><div class="status-label" style="margin-bottom:6px; color:#94a3b8;">🔥 Outperforming Sectors (vs Nifty)</div><div style="display:flex; flex-wrap:wrap; gap:6px;">{pills if pills else "No trending sectors detected"}</div></div>'

    st.markdown(
        f'<div class="glass-card" style="margin: 8px 0 18px;">'
        f'<div class="panel-title">Scanner Status</div>'
        f'<div class="status-grid">'
        f'<div class="status-cell"><div class="status-label">Source</div><div class="status-value">{source_label}</div></div>'
        f'<div class="status-cell"><div class="status-label">Last Run</div><div class="status-value">{time_label}</div></div>'
        f'<div class="status-cell"><div class="status-label">Total Results</div><div class="status-value">{total_results}</div></div>'
        f'<div class="status-cell"><div class="status-label">Visible After Filters</div><div class="status-value">{filtered_count}</div></div></div>'
        f'{sector_section}</div>',
        unsafe_allow_html=True,
    )


def _render_metrics(results: pd.DataFrame, stats: Optional[dict], scan_time: Optional[str]) -> None:
    total_hits = len(results)
    scanned = (stats or {}).get("scanned", 0)
    avg_rsi = results["RSI"].mean() if "RSI" in results else 0
    avg_strength = results["Signal_Strength"].mean() if "Signal_Strength" in results else 0
    pass_rate = total_hits / max(scanned, 1) * 100
    
    sector_scores = (stats or {}).get("sector_sentiment", {})
    best_sector = "Neutral"
    if sector_scores:
        bs = max(sector_scores, key=sector_scores.get)
        if sector_scores[bs] > 6: best_sector = f"{bs} ({sector_scores[bs]})"

    st.markdown(
        f'<div class="metric-row">'
        f'<div class="metric-card">'
        f'<div class="metric-label">Opportunities</div>'
        f'<div class="metric-value" style="color:#00e5ff;">{total_hits}</div>'
        f'<div class="metric-delta neutral">of {scanned} scanned</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label">Pass Rate</div>'
        f'<div class="metric-value">{pass_rate:.1f}<span style="font-size:0.9rem;">%</span></div>'
        f'<div class="metric-delta neutral">quality filter</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label">Avg RSI</div>'
        f'<div class="metric-value" style="color:{"#ffca28" if avg_rsi > 70 else "#00e676"};">{avg_rsi:.0f}</div>'
        f'<div class="metric-delta neutral">momentum zone</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label">Avg Strength</div>'
        f'<div class="metric-value">{avg_strength:.1f}<span style="font-size:0.9rem;">/10</span></div>'
        f'<div class="metric-delta {"up" if avg_strength >= 6 else "down"}">{"Strong" if avg_strength >= 6 else "Moderate"}</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label">Market Context</div>'
        f'<div class="metric-value" style="color:#00ffaa; font-size:1.1rem;">{best_sector}</div>'
        f'<div class="metric-delta neutral">trending sectors</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label">Scan Time</div>'
        f'<div class="metric-value" style="font-size:0.9rem;">{(scan_time or "–")[-8:]}</div>'
        f'<div class="metric-delta neutral">{(scan_time or "–")[:10]}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_filter_breakdown(stats: Optional[dict]) -> None:
    if not stats or stats.get("scanned", 0) <= 0:
        return
    with st.expander("📉 Filter Breakdown", expanded=False):
        columns = st.columns(7)
        for column, (label, key) in zip(
            columns,
            [
                ("Trend", "trend_fail"),
                ("Volume", "volume_fail"),
                ("Momentum", "momentum_fail"),
                ("ADX", "adx_fail"),
                ("MACD", "macd_fail"),
                ("B.Bands", "bb_fail"),
                ("Fakeouts", "fakeout_trap"),
            ],
        ):
            column.metric(f"❌ {label}", stats.get(key, 0))


def _render_watchlist_quick_add(results: pd.DataFrame) -> None:
    top_3 = results.head(3)["Ticker"].tolist()
    selected_tickers = st.multiselect(
        "Quick-add to Watchlist",
        options=results["Ticker"].tolist(),
        default=top_3,
        help="Select tickers then click ➕",
    )
    add_col, _ = st.columns([1, 3])
    with add_col:
        if st.button("➕ Add to Watchlist", key="qk_add"):
            added = 0
            for ticker in selected_tickers:
                if ticker not in st.session_state.watchlist:
                    st.session_state.watchlist.append(ticker)
                    added += 1
            st.success(f"Added {added} ticker(s)")


def _render_detail_view(results, selection, load_ticker_history, chart_options) -> None:
    selected_rows = selection.get("selection", {}).get("rows", [])
    if not selected_rows:
        return False

    row = results.iloc[selected_rows[0]].to_dict()
    ticker = row.get("Ticker", "")
    ltp = float(row.get("LTP", 0))
    sector_score = row.get("Sector_Score", 5.0)
    atr = float(row.get("ATR", ltp * 0.015))
    sect_color = "#00e676" if sector_score >= 8.0 else ("#ffca28" if sector_score >= 5 else "#ff5252")
    sect_label = "Strong Bullish" if sector_score >= 8.5 else ("Bullish" if sector_score >= 6.5 else ("Weak" if sector_score <= 4 else "Neutral"))

    signal_strength = int(row.get("Signal_Strength", 0))
    entry = ltp
    rs_value = row.get("RS_Rating", 100)
    stop_loss = ltp - 1.5 * atr
    target_1 = ltp + 1.0 * atr
    target_2 = ltp + 3.0 * atr
    target_3 = ltp + 5.0 * atr
    risk = entry - stop_loss
    risk_reward = (target_2 - entry) / risk if risk > 0 else 0
    support_1 = row.get("_Support1", ltp - 2 * atr)
    support_2 = row.get("_Support2", ltp - 4 * atr)

    st.markdown(
        f'<div class="trade-card">'
        f'<div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">'
        f'<div class="trade-ticker">{ticker}</div>'
        f'<div style="background:rgba(0,229,255,0.1);border:1px solid rgba(0,229,255,0.25);border-radius:20px;padding:2px 10px;font-size:0.75rem;color:#00e5ff;">{row.get("Type", "")}</div>'
        f'<div style="background:{"rgba(0,230,118,0.12)" if signal_strength >= 7 else "rgba(255,202,40,0.12)"};border:1px solid {"rgba(0,230,118,0.3)" if signal_strength >= 7 else "rgba(255,202,40,0.3)"};border-radius:20px;padding:2px 10px;font-size:0.75rem;color:{"#00e676" if signal_strength >= 7 else "#ffca28"};">⚡ {signal_strength}/10 Signal</div>'
        f'<div style="background:{sect_color}1a; border:1px solid {sect_color}44; border-radius:20px; padding:2px 10px; font-size:0.75rem; color:{sect_color};">Sector: {sect_label} ({sector_score})</div>'
        f'<div style="background:rgba(124,77,255,0.1);border:1px solid rgba(124,77,255,0.3);border-radius:20px;padding:2px 10px;font-size:0.75rem;color:#7c4dff;">RS: {rs_value}</div></div>'
        f'<div class="trade-subtitle">{row.get("Pattern", "")}</div>'
        f'<div class="level-grid">'
        f'<div class="level-box"><div class="level-label">Entry</div><div class="level-value level-entry">₹{entry:,.2f}</div></div>'
        f'<div class="level-box"><div class="level-label">Stop Loss  (1.5×ATR)</div><div class="level-value level-sl">₹{stop_loss:,.2f}</div><div style="font-size:0.7rem;color:#ff5252;margin-top:2px;">−₹{risk:.2f}</div></div>'
        f'<div class="level-box"><div class="level-label">Target 1  (1×ATR)</div><div class="level-value level-tp1">₹{target_1:,.2f}</div><div style="font-size:0.7rem;color:#ffca28;margin-top:2px;">+₹{(target_1 - entry):.2f}</div></div>'
        f'<div class="level-box"><div class="level-label">Target 2  (3×ATR)</div><div class="level-value level-tp2">₹{target_2:,.2f}</div><div style="font-size:0.7rem;color:#00e676;margin-top:2px;">+₹{(target_2 - entry):.2f} · RR {risk_reward:.1f}×</div></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    signals = {
        "MACD": row.get("MACD") == "✅",
        "BB Zone": row.get("BB") == "✅",
        "VWAP": row.get("VWAP") == "✅",
        "Divergence": "Bull" in str(row.get("Divergence", "")),
        "Vol Spike": row.get("Vol_Spike") in ["✅", "🔥 SURGE"],
    }
    pills = "".join(
        [
            f"<span class='signal-pill {'sp-yes' if value else 'sp-no'}'>{'✓' if value else '✗'} {name}</span>"
            for name, value in signals.items()
        ]
    )
    confidence = min(signal_strength / 10 * 100, 100)
    bar_color = "#00e676" if confidence >= 70 else "#ffca28" if confidence >= 50 else "#ff5252"

    st.markdown(
        f'<div class="glass-card">'
        f'<div class="panel-title">Signal Confirmations</div>'
        f'<div style="margin-bottom:12px;">{pills}</div>'
        f'<div style="display:flex;align-items:center;gap:12px;">'
        f'<div style="font-size:0.78rem;color:#8899bb;">Confidence</div>'
        f'<div class="strength-bar-wrap" style="flex:1;">'
        f'<div class="strength-bar" style="width:{confidence:.0f}%;background:{bar_color};"></div></div>'
        f'<div style="font-size:0.82rem;font-family:{"JetBrains Mono"};color:{bar_color};">{confidence:.0f}%</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    support_col_1, support_col_2, support_col_3 = st.columns(3)
    support_col_1.metric("Support 1 (BB Lower)", f"₹{support_1:,.2f}")
    support_col_2.metric("Support 2 (SMA 200)", f"₹{support_2:,.2f}")
    support_col_3.metric("Extended Target (5×ATR)", f"₹{target_3:,.2f}", delta=f"+₹{(target_3 - entry):.2f}")

    with st.expander("🧮 Position Sizer", expanded=False):
        size_col_1, size_col_2, size_col_3 = st.columns(3)
        account = size_col_1.number_input("Account Size (₹)", 10_000, 10_000_000, 100_000, 10_000, key=f"acct_{ticker}")
        risk_pct = size_col_2.number_input("Risk per Trade (%)", 0.25, 5.0, 1.0, 0.25, key=f"rpct_{ticker}")
        size_col_3.number_input("Max Portfolio Risk (%)", 1.0, 20.0, 5.0, 0.5, key=f"mrisk_{ticker}")
        risk_amount = account * risk_pct / 100
        quantity = int(risk_amount // risk) if risk > 0 else 0
        position_value = quantity * entry
        metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
        metric_col_1.metric("Risk Amount", f"₹{risk_amount:,.0f}")
        metric_col_2.metric("Shares to Buy", quantity)
        metric_col_3.metric("Position Value", f"₹{position_value:,.0f}")
        metric_col_4.metric("Portfolio %", f"{position_value / account * 100:.1f}%")

        exit_df = pd.DataFrame(
            {
                "Level": ["Stop Loss", "Target 1", "Target 2", "Target 3"],
                "Price": [f"₹{stop_loss:.2f}", f"₹{target_1:.2f}", f"₹{target_2:.2f}", f"₹{target_3:.2f}"],
                "P&L": [
                    f"−₹{risk * quantity:,.0f}",
                    f"+₹{(target_1 - entry) * quantity:,.0f}",
                    f"+₹{(target_2 - entry) * quantity:,.0f}",
                    f"+₹{(target_3 - entry) * quantity:,.0f}",
                ],
                "RR": [
                    "—",
                    f"1:{(target_1 - entry) / risk:.1f}",
                    f"1:{(target_2 - entry) / risk:.1f}",
                    f"1:{(target_3 - entry) / risk:.1f}",
                ],
            }
        )
        st.dataframe(exit_df, use_container_width=True, hide_index=True)

    with st.spinner(f"Loading chart for {ticker}…"):
        df_chart = load_ticker_history(ticker)
    if not df_chart.empty:
        fig = build_chart(
            df_chart,
            ticker,
            row,
            show_sma=chart_options.show_sma,
            show_ema=chart_options.show_ema,
            show_bb=chart_options.show_bb,
            show_rsi=chart_options.show_rsi,
            show_macd=chart_options.show_macd,
            show_vwap=chart_options.show_vwap,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Chart data unavailable for this ticker.")

    if st.button("➕ Add to Watchlist", key=f"aw_{ticker}"):
        if ticker not in st.session_state.watchlist:
            st.session_state.watchlist.append(ticker)
            st.success(f"{ticker} added to watchlist!")
        else:
            st.info("Already in watchlist.")
    return True


def _render_results_blotter(filtered_results: pd.DataFrame):
    display_columns = [
        "Ticker",
        "LTP",
        "ROE",
        "Sector",
        "Sector_Score",
        "Mkt_Cap_Cr",
        "Pattern",
        "RS_Rating",
        "Vol_x",
        "RSI",
        "Signal_Strength",
        "MACD",
        "BB",
        "VWAP",
    ]
    available_columns = [column for column in display_columns if column in filtered_results.columns]
    rendered_df = filtered_results[available_columns].rename(
        columns={
            "Signal_Strength": "Strength",
            "Vol_x": "Vol×",
            "Vol_Spike": "Spike",
            "Type": "Level",
            "RS_Rating": "RS",
            "Sector_Score": "Sect.Score",
        }
    ).copy()

    styled = style_scanner_results(rendered_df)
    try:
        return st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
    except Exception:
        return st.dataframe(
            rendered_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )


def render_tab(settings, chart_options, load_ticker_history, fetch_indices_performance) -> None:
    results = st.session_state.results
    stats = st.session_state.stats
    scan_time = st.session_state.last_scan_time
    need_scan = st.session_state.get("run_scan", False)
    status_placeholder = st.empty()

    if settings.use_cache and need_scan:
        results, stats, scan_time = scanner_service.fetch_cached_data(True)
        if results is not None:
            st.session_state.update(
                results=results,
                stats=stats,
                last_scan_time=scan_time,
                run_scan=False,
                scan_source="Cache",
            )
            status_placeholder.success(f"✅ Loaded from cache · {scan_time}")
        else:
            st.session_state.run_scan = False
            status_placeholder.warning("No cached scan found in the last 12 hours. Click Fresh Scan to generate one.")

    if not settings.use_cache and results is not None and not need_scan:
        status_placeholder.info("ℹ️ Showing previous scan. Click Run Fresh Scan to refresh.")

    if not settings.use_cache and need_scan:
        progress_bar = st.progress(0.0)
        progress_text = st.empty()

        def _progress(progress_value: float) -> None:
            progress_bar.progress(min(progress_value, 1.0))
            progress_text.markdown(
                f"<div style='color:#8899bb;font-size:0.8rem;font-family:JetBrains Mono;'>Scanning · {int(progress_value * 100)}%</div>",
                unsafe_allow_html=True,
            )

        with st.spinner("Downloading market data from Yahoo Finance…"):
            effective_market_cap = settings.min_mkt_cap if settings.universe == "Total Market (Cap Focused)" else 0
            sector_map = get_sector_mapping(settings.universe)
            results, stats, scan_time = scanner_service.perform_fresh_scan(
                settings.universe,
                settings.vol_thresh,
                settings.rsi_range,
                settings.dist_thresh,
                effective_market_cap,
                sector_map,
                _progress,
            )
        progress_bar.empty()
        progress_text.empty()
        st.session_state.update(
            results=results,
            stats=stats,
            last_scan_time=scan_time.split(" ")[1] if " " in scan_time else scan_time,
            run_scan=False,
            scan_source="Live",
        )
        status_placeholder.success(f"✅ Scan complete · {scan_time}")
    elif settings.use_cache and results is not None and not need_scan:
        status_placeholder.info("ℹ️ Showing previous results. Click Load Cached Scan to refresh from cache.")

    filtered_results = _apply_result_filters(results)

    if results is not None and len(results) > 0:
        _render_status_banner(
            results, filtered_results, st.session_state.last_scan_time, 
            st.session_state.get("scan_source"), stats
        )
        render_top_picks(filtered_results if filtered_results is not None and len(filtered_results) > 0 else results)
        _render_metrics(results, stats, scan_time)
        _render_filter_breakdown(stats)
        _render_watchlist_quick_add(results)
        st.caption("Select one row from the blotter to open the detailed setup, chart, and position sizing workspace.")

        if filtered_results is not None and len(filtered_results) == 0:
            st.warning("Your current post-scan filters hide all results. Relax Min Strength, RSI, or Volume × to see matches.")
            return

        blotter_col, workspace_col = st.columns([1.15, 0.85], gap="medium")
        with blotter_col:
            st.markdown(
                f"""
                <div class="terminal-panel">
                    <div class="terminal-head">
                        <div>
                            <div class="terminal-title">Signal Blotter</div>
                            <div class="terminal-subtitle">Ranked breakout candidates after post-scan filtering</div>
                        </div>
                        <div class="terminal-badge">{len(filtered_results)} MATCHES</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )
            selection = _render_results_blotter(filtered_results)
            st.markdown("</div>", unsafe_allow_html=True)

        with workspace_col:
            st.markdown(
                """
                <div class="terminal-panel">
                    <div class="terminal-head">
                        <div>
                            <div class="terminal-title">Setup Workspace</div>
                            <div class="terminal-subtitle">Levels, confirmations, chart context, and sizing</div>
                        </div>
                        <div class="terminal-badge">DETAIL</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )
            has_selection = _render_detail_view(filtered_results.reset_index(drop=True), selection, load_ticker_history, chart_options)
            if not has_selection:
                st.info("Pick a stock from the blotter to open the setup workspace.")
            st.markdown("</div>", unsafe_allow_html=True)
    elif results is not None and len(results) == 0:
        st.info("No high-conviction opportunities match current filters. Try relaxing the parameters.", icon="ℹ️")
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:48px 24px;">'
            '<div style="font-size:3rem;margin-bottom:12px;">⚡</div>'
            '<div style="font-size:1.1rem;font-weight:600;color:#00e5ff;margin-bottom:8px;">Scanner is standing by</div>'
            '<div style="color:#8899bb;font-size:0.9rem;">Choose Fresh Scan or Use Cache in the sidebar, then click the action button to start.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
