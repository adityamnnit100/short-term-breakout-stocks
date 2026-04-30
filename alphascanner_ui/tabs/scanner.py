"""Scanner tab UI."""

from typing import Optional

import pandas as pd
import streamlit as st

import scanner_service
from alphascanner_ui.auth import save_current_user_workspace
from alphascanner_ui.charts import build_chart, render_top_picks, style_scanner_results
from alphascanner_ui.data import fetch_fii_dii_data, fetch_indices_performance, get_sector_mapping
from alphascanner_ui.services.alerts_service import get_alerts_service


def _calculate_execution_status(row: dict) -> str:
    risk_grade = str(row.get("Risk_Grade", "")).strip()
    market_health = str(row.get("Market_Health", "")).strip()
    strength = float(row.get("Signal_Strength", 0) or 0)
    stop_pct = float(row.get("Stop_%", 999) or 999)

    if market_health == "Risk-Off" or risk_grade == "Reduce/Skip" or stop_pct > 8 or strength < 7:
        return "Caution"
    if risk_grade in {"A", "B"} and market_health in {"Risk-On", "Constructive"} and stop_pct <= 8 and strength >= 7:
        return "Ready"
    if risk_grade == "C":
        return "Watch"
    return "Review"


@st.dialog("Full Screen Chart", width="large")
def show_full_chart(fig) -> None:
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )


def _apply_result_filters(results: pd.DataFrame) -> pd.DataFrame:
    if results is None or results.empty:
        return results

    with st.expander("Refine Visible Results", expanded=False):
        st.caption("These controls only narrow the current scan output. They do not rerun the scanner.")
        fcol1, fcol2, fcol3, fcol4, fcol5, fcol6, fcol7, fcol8 = st.columns(8)
        min_strength = fcol1.slider("Min Strength", 0, 10, 1)
        min_rsi = fcol2.slider("Min RSI", 0, 100, 50) if "RSI" in results.columns else None
        min_vol = fcol3.slider("Min Volume ×", 1.0, 5.0, 1.0) if "Vol_x" in results.columns else None
        min_base = fcol4.slider("Min Base (Weeks)", 0, 20, 0) if "Base_Weeks" in results.columns else None
        max_stop = fcol5.slider("Max Stop %", 1.0, 15.0, 8.0, 0.5) if "Stop_%" in results.columns else None
        risk_choices = fcol6.multiselect(
            "Risk Grade",
            ["A", "B", "C", "Reduce/Skip"],
            default=["A", "B", "C"],
        ) if "Risk_Grade" in results.columns else None
        breadth_choices = fcol7.multiselect(
            "Breadth",
            ["Any", "Risk-On", "Constructive", "Caution", "Risk-Off"],
            default=["Any"],
        ) if "Market_Health" in results.columns else None
        execution_choices = fcol8.multiselect(
            "Execution",
            ["Any", "Ready", "Caution", "Watch", "Review"],
            default=["Any"],
        ) if {"Risk_Grade", "Market_Health", "Signal_Strength", "Stop_%"}.issubset(results.columns) else None

    mask = results["Signal_Strength"] >= min_strength

    if min_rsi is not None:
        mask &= (results["RSI"] >= min_rsi)
    if min_vol is not None:
        mask &= (results["Vol_x"] >= min_vol)
    if min_base is not None:
        mask &= (results["Base_Weeks"] >= min_base)
    if max_stop is not None:
        mask &= (results["Stop_%"] <= max_stop)
    if risk_choices:
        mask &= results["Risk_Grade"].isin(risk_choices)
    if breadth_choices and "Any" not in breadth_choices:
        mask &= results["Market_Health"].isin(breadth_choices)

    if st.session_state.get("only_ready_setups", False) and {"Risk_Grade", "Market_Health", "Signal_Strength", "Stop_%"}.issubset(results.columns):
        execution_series = results.apply(_calculate_execution_status, axis=1)
        mask &= execution_series.eq("Ready")

    if execution_choices and "Any" not in execution_choices:
        execution_series = results.apply(_calculate_execution_status, axis=1)
        mask &= execution_series.isin(execution_choices)

    return results[mask]


def _render_status_banner(
    results: Optional[pd.DataFrame],
    filtered_results: Optional[pd.DataFrame],
    scan_time: Optional[str],
    scan_source: Optional[str],
    stats: Optional[dict] = None,
    timeframe: Optional[str] = None,
) -> None:
    total_results = 0 if results is None else len(results)
    filtered_count = 0 if filtered_results is None else len(filtered_results)
    source_label = scan_source or "None"
    time_label = scan_time or "Never"
    timeframe_label = "Daily" if timeframe == "1d" else (timeframe or "Daily")

    trending = (stats or {}).get("trending_sectors", [])
    sector_scores = (stats or {}).get("sector_sentiment", {})

    pills = ""
    for s in trending:
        score = sector_scores.get(s, 5.0)
        color = "#00ffaa" if score >= 8 else ("#ffca28" if score >= 5 else "#ff5252")
        pills += f'<span class="mini-tag" style="background:rgba(0,0,0,0.3); color:{color}; border:1px solid {color}66; margin-top:4px; display:inline-block;">{s} ({score})</span>'

    market_health = (stats or {}).get("market_health", "Unknown")
    market_bias = (stats or {}).get("market_bias", "Neutral")
    sector_section = f'<div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(128,128,128,0.2);"><div class="status-label" style="margin-bottom:6px; color:#94a3b8;">🔥 Outperforming Sectors (vs Nifty)</div><div style="display:flex; flex-wrap:wrap; gap:6px;">{pills if pills else "No trending sectors detected"}</div></div>'

    st.markdown(
        f'<div class="glass-card" style="margin: 8px 0 18px;">'
        f'<div class="panel-title" style="color: #00e5ff;">Scanner Status</div>'
        f'<div class="status-grid">'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Source</div><div class="status-value" style="color: #00e5ff;">{source_label}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Last Run</div><div class="status-value" style="color: #00e5ff;">{time_label}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Timeframe</div><div class="status-value" style="color: #00e5ff;">{timeframe_label}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Total Results</div><div class="status-value" style="color: #00e5ff;">{total_results}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Visible After Filters</div><div class="status-value" style="color: #00e5ff;">{filtered_count}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Market Breadth</div><div class="status-value" style="color: #00e5ff;">{market_health}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Market Bias</div><div class="status-value" style="color: #00e5ff;">{market_bias}</div></div></div>'
        f'{sector_section}</div>',
        unsafe_allow_html=True,
    )


def _render_metrics(results: pd.DataFrame, stats: Optional[dict], scan_time: Optional[str]) -> None:
    total_hits = len(results)
    scanned = (stats or {}).get("scanned", 0)
    universe_size = (stats or {}).get("universe_size") or scanned
    universe_label = (stats or {}).get("universe") or "Universe"
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
        f'<div class="metric-label" style="color: #94a3b8;">Opportunities</div>'
        f'<div class="metric-value" style="color:#00e5ff;">{total_hits}</div>'
        f'<div class="metric-delta neutral" style="color: #64748b;">{scanned}/{universe_size} eligible · {universe_label}</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label" style="color: #94a3b8;">Pass Rate</div>'
        f'<div class="metric-value" style="color: #00e5ff;">{pass_rate:.1f}<span style="font-size:0.9rem;">%</span></div>'
        f'<div class="metric-delta neutral" style="color: #64748b;">quality filter</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label" style="color: #94a3b8;">Avg RSI</div>'
        f'<div class="metric-value" style="color:{"#ffca28" if avg_rsi > 70 else "#00e676"};">{avg_rsi:.0f}</div>'
        f'<div class="metric-delta neutral" style="color: #64748b;">momentum zone</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label" style="color: #94a3b8;">Avg Strength</div>'
        f'<div class="metric-value" style="color: #00e5ff;">{avg_strength:.1f}<span style="font-size:0.9rem;">/10</span></div>'
        f'<div class="metric-delta {"up" if avg_strength >= 6 else "down"}">{"Strong" if avg_strength >= 6 else "Moderate"}</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label" style="color: #94a3b8;">Market Context</div>'
        f'<div class="metric-value" style="color:#00ffaa; font-size:1.1rem;">{best_sector}</div>'
        f'<div class="metric-delta neutral" style="color: #64748b;">trending sectors</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label" style="color: #94a3b8;">Scan Time</div>'
        f'<div class="metric-value" style="font-size:0.9rem; color: #00e5ff;">{(scan_time or "–")[-8:]}</div>'
        f'<div class="metric-delta neutral" style="color: #64748b;">{(scan_time or "–")[:10]}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_macro_context(stats: Optional[dict]) -> None:
    if not stats:
        return

    fii_dii = fetch_fii_dii_data()
    indices = fetch_indices_performance()
    nifty = indices.get("Nifty 50", {})
    bank_nifty = indices.get("Bank Nifty", {})
    trending = stats.get("trending_sectors", [])
    sector_rotation = ", ".join(trending[:3]) if trending else "No strong rotation"
    if len(trending) > 3:
        sector_rotation += f" +{len(trending) - 3} more"

    bias_label = "Neutral"
    if nifty.get("change", 0) > 0 and bank_nifty.get("change", 0) > 0:
        bias_label = "Bullish"
    elif nifty.get("change", 0) < 0 and bank_nifty.get("change", 0) < 0:
        bias_label = "Bearish"
    else:
        bias_label = "Mixed"

    fii_net = fii_dii.get("fii_net", 0)
    dii_net = fii_dii.get("dii_net", 0)
    fii_display = "N/A" if fii_net == 0 else f"₹{fii_net:,.0f} Cr"
    fii_delta = "N/A" if fii_net == 0 else f"{fii_net:+.0f}"
    dii_display = "N/A" if dii_net == 0 else f"₹{dii_net:,.0f} Cr"
    dii_delta = "N/A" if dii_net == 0 else f"{dii_net:+.0f}"

    st.markdown(
        '<div class="glass-card" style="margin-top: 16px; padding: 14px;">'
        '<div class="panel-title" style="color: #ffca28;">Market Context</div>'
        '<div class="status-grid" style="grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;">'
        f'<div class="status-cell"><div class="status-label">Nifty Bias</div><div class="status-value">{bias_label}</div><div class="status-delta">{nifty.get("change", 0):+.2f}%</div></div>'
        f'<div class="status-cell"><div class="status-label">Bank Nifty</div><div class="status-value">{bank_nifty.get("change", 0):+.2f}%</div><div class="status-delta">{bank_nifty.get("price", "N/A")}</div></div>'
        f'<div class="status-cell"><div class="status-label">FII Net Flow</div><div class="status-value">{fii_display}</div><div class="status-delta">{fii_delta}</div></div>'
        f'<div class="status-cell"><div class="status-label">DII Net Flow</div><div class="status-value">{dii_display}</div><div class="status-delta">{dii_delta}</div></div>'
        '</div>'
        f'<div style="margin-top: 12px; color: #94a3b8;">Sector Rotation: {sector_rotation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_filter_breakdown(stats: Optional[dict]) -> None:
    if not stats or stats.get("scanned", 0) <= 0:
        return
    with st.expander("📉 Filter Breakdown", expanded=False):
        columns = st.columns(9)
        for column, (label, key) in zip(
            columns,
            [
                ("Trend", "trend_fail"),
                ("Liquidity", "liquidity_fail"),
                ("Volume", "volume_fail"),
                ("Momentum", "momentum_fail"),
                ("ADX", "adx_fail"),
                ("MACD", "macd_fail"),
                ("B.Bands", "bb_fail"),
                ("Fakeouts", "fakeout_trap"),
                ("Errors", "error_fail"),
            ],
        ):
            column.metric(f"❌ {label}", stats.get(key, 0))


def _render_watchlist_quick_add(results: pd.DataFrame) -> None:
    if isinstance(st.session_state.get("watchlist"), list):
        st.session_state.watchlist = {"Default": st.session_state.watchlist}
    elif not isinstance(st.session_state.get("watchlist"), dict):
        st.session_state.watchlist = {"Default": []}

    watchlist_names = list(st.session_state.watchlist.keys())

    col1, col2 = st.columns([1, 1])
    target_wl = col1.selectbox("Target Watchlist", options=watchlist_names, help="Select an existing list")
    new_wl_name = col2.text_input("OR Create New", placeholder="New list name...", help="Type to create and add")

    top_3 = results.head(3)["Ticker"].tolist() if not results.empty else []
    selected_tickers = st.multiselect(
        "Quick-add to Watchlist",
        options=results["Ticker"].tolist(),
        default=top_3,
    )

    if st.button("➕ Add to Watchlist", key="qk_add", use_container_width=True):
        final_wl = new_wl_name.strip() if new_wl_name.strip() else target_wl
        if final_wl not in st.session_state.watchlist:
            st.session_state.watchlist[final_wl] = []

        added = 0
        for ticker in selected_tickers:
            if ticker not in st.session_state.watchlist[final_wl]:
                st.session_state.watchlist[final_wl].append(ticker)
                added += 1
        if added:
            save_current_user_workspace()
        st.success(f"Added {added} ticker(s) to '{final_wl}'")


def _maybe_send_scan_alerts(results: pd.DataFrame, scanner_type: str) -> None:
    if results is None or results.empty or not st.session_state.get("alerts_enabled"):
        return
    has_telegram = st.session_state.get("telegram_token") and st.session_state.get("telegram_chat_id")
    has_whatsapp = st.session_state.get("whatsapp_webhook_url")
    if not has_telegram and not has_whatsapp:
        return

    service = get_alerts_service(
        st.session_state.get("telegram_token"),
        st.session_state.get("telegram_chat_id"),
        st.session_state.get("whatsapp_webhook_url"),
    )
    sent_keys = st.session_state.setdefault("sent_alert_keys", set())
    if not isinstance(sent_keys, set):
        sent_keys = set(sent_keys)
        st.session_state.sent_alert_keys = sent_keys

    for _, row in results.head(10).iterrows():
        ticker = str(row.get("Ticker", ""))
        if not ticker:
            continue
        ltp = float(row.get("LTP", 0) or 0)
        volume = float(row.get("Vol_x", 0) or 0)
        resistance = float(row.get("_Resistance", row.get("Entry", ltp)) or ltp)
        setup_score = row.get("Setup_Score")

        if scanner_type == "Pre-Breakout":
            if not st.session_state.get("alert_breakout", True):
                continue
            threshold = float(st.session_state.get("alert_pre_breakout_score", 7) or 7)
            if setup_score is None or float(setup_score) < threshold:
                continue
            alert_key = f"pre:{ticker}:{setup_score}:{ltp:.2f}"
            if alert_key not in sent_keys and service.send_breakout_alert(ticker, ltp, resistance, volume, float(setup_score)):
                sent_keys.add(alert_key)
        elif scanner_type == "Breakout" and st.session_state.get("alert_breakout", True):
            alert_key = f"bo:{ticker}:{ltp:.2f}"
            if alert_key not in sent_keys and service.send_breakout_alert(ticker, ltp, resistance, volume):
                sent_keys.add(alert_key)


def _render_detail_view(results, selection, load_ticker_history, chart_options, timeframe: str = "1d") -> None:
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
    rr_label = lambda target: f"1:{(target - entry) / risk:.1f}" if risk > 0 else "—"
    stop_pct = risk / entry * 100 if entry > 0 else 0
    target_2_pct = (target_2 - entry) / entry * 100 if entry > 0 else 0
    support_1 = row.get("_Support1", ltp - 2 * atr)
    support_2 = row.get("_Support2", ltp - 4 * atr)
    vol_ratio = float(row.get("Vol_x", 0) or 0)
    risk_grade = row.get("Risk_Grade", "C")
    qty_1l = int(row.get("Qty_1L_1pct", 0) or 0)
    market_health = row.get("Market_Health", "Unknown")
    execution_status = _calculate_execution_status(row)
    execution_label = (
        "Preferred" if risk_grade == "A" else
        "Tradable" if risk_grade == "B" else
        "Small Size" if risk_grade == "C" else
        "Avoid / Wait"
    )

    st.markdown(
        f'<div class="trade-card">'
        f'<div style="display:flex; align-items:center; gap:14px; margin-bottom:4px;">'
        f'<div class="trade-ticker" style="color: #00e5ff;">{ticker}</div>'
        f'<div style="background:rgba(0,229,255,0.1);border:1px solid rgba(0,229,255,0.25);border-radius:20px;padding:2px 10px;font-size:0.75rem;color:#00e5ff;">{row.get("Type", "")}</div>'
        f'<div style="background:{"rgba(0,230,118,0.12)" if signal_strength >= 7 else "rgba(255,202,40,0.12)"};border:1px solid {"rgba(0,230,118,0.3)" if signal_strength >= 7 else "rgba(255,202,40,0.3)"};border-radius:20px;padding:2px 10px;font-size:0.75rem;color:{"#00e676" if signal_strength >= 7 else "#ffca28"};">⚡ {signal_strength}/10 Signal</div>'
        f'<div style="background:{sect_color}1a; border:1px solid {sect_color}44; border-radius:20px; padding:2px 10px; font-size:0.75rem; color:{sect_color};">Sector: {sect_label} ({sector_score})</div>'
        f'<div style="background:rgba(124,77,255,0.1);border:1px solid rgba(124,77,255,0.3);border-radius:20px;padding:2px 10px;font-size:0.75rem;color:#7c4dff;">RS: {rs_value}</div>'
        f'<div style="background:rgba(255,202,40,0.1);border:1px solid rgba(255,202,40,0.3);border-radius:20px;padding:2px 10px;font-size:0.75rem;color:#ffca28;">Risk: {risk_grade}</div></div>'
        f'<div class="trade-subtitle" style="color: #94a3b8;">{row.get("Pattern", "")}</div>'
        f'<div style="margin-top:8px;padding:8px 10px;border-left:3px solid #0284c7;background:#f8fafc;color:#0f172a;font-size:0.82rem;">Execution stance: <b>{execution_label}</b> · Breadth: <b>{market_health}</b> · Short-term status: <b>{execution_status}</b> · Suggested qty for ₹1L / 1% risk: <b>{qty_1l}</b></div>'
        f'<div class="level-grid">'
        f'<div class="level-box"><div class="level-label" style="color: #94a3b8;">Entry</div><div class="level-value level-entry" style="color: #00e5ff;">₹{entry:,.2f}</div></div>'
        f'<div class="level-box"><div class="level-label" style="color: #94a3b8;">Stop Loss  (1.5×ATR)</div><div class="level-value level-sl" style="color: #ff5252;">₹{stop_loss:,.2f}</div><div style="font-size:0.7rem;color:#ff5252;margin-top:2px;">−₹{risk:.2f}</div></div>'
        f'<div class="level-box"><div class="level-label" style="color: #94a3b8;">Target 1  (1×ATR)</div><div class="level-value level-tp1" style="color: #ffca28;">₹{target_1:,.2f}</div><div style="font-size:0.7rem;color:#ffca28;margin-top:2px;">+₹{(target_1 - entry):.2f}</div></div>'
        f'<div class="level-box"><div class="level-label" style="color: #94a3b8;">Target 2  (3×ATR)</div><div class="level-value level-tp2" style="color: #00e676;">₹{target_2:,.2f}</div><div style="font-size:0.7rem;color:#00e676;margin-top:2px;">+₹{(target_2 - entry):.2f} · RR {risk_reward:.1f}×</div></div>'
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
        f'<div class="panel-title" style="color: #00e5ff;">Signal Confirmations</div>'
        f'<div style="margin-bottom:12px;">{pills}</div>'
        f'<div style="display:flex;align-items:center;gap:12px;">'
        f'<div style="font-size:0.78rem;color:#8899bb;">Confidence</div>'
        f'<div class="strength-bar-wrap" style="flex:1; background: rgba(128,128,128,0.2);">'
        f'<div class="strength-bar" style="width:{confidence:.0f}%;background:{bar_color};"></div></div>'
        f'<div style="font-size:0.82rem;font-family:{"JetBrains Mono"};color:{bar_color};">{confidence:.0f}%</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    support_col_1, support_col_2, support_col_3 = st.columns(3)
    support_col_1.metric("Support 1 (20-SMA)", f"₹{support_1:,.2f}")
    support_col_2.metric("Support 2 (SMA 200)", f"₹{support_2:,.2f}")
    support_col_3.metric("Extended Target (5×ATR)", f"₹{target_3:,.2f}", delta=f"+₹{(target_3 - entry):.2f}")

    with st.expander("Short-Term Trade Guardrails", expanded=True):
        guard_col_1, guard_col_2, guard_col_3, guard_col_4 = st.columns(4)
        guard_col_1.metric("Stop Distance", f"{stop_pct:.1f}%")
        guard_col_2.metric("Target 2 Upside", f"{target_2_pct:.1f}%")
        guard_col_3.metric("Risk / Reward", f"1:{risk_reward:.1f}")
        guard_col_4.metric("Volume Confirmation", f"{vol_ratio:.1f}×")
        risk_col_1, risk_col_2, risk_col_3 = st.columns(3)
        execution_status = _calculate_execution_status(row)

        risk_col_1, risk_col_2, risk_col_3, risk_col_4 = st.columns(4)
        risk_col_1.metric("Model Risk Grade", risk_grade)
        risk_col_2.metric("Qty @ ₹1L / 1% Risk", qty_1l)
        risk_col_3.metric("Market Breadth", market_health)
        risk_col_4.metric("Short-Term Status", execution_status)

        checks = [
            ("Risk/reward is at least 1:2", risk_reward >= 2),
            ("Stop is volatility-based, not arbitrary", atr > 0 and risk > 0),
            ("Volume confirms participation", vol_ratio >= 1.5),
            ("Signal strength is high enough for short-term focus", signal_strength >= 7),
            ("Avoid chase if stop is wider than 8%", stop_pct <= 8),
            ("Market breadth is not risk-off", market_health != "Risk-Off"),
            ("Trade readiness is acceptable for intraday/short-term", execution_status == "Ready"),
        ]
        checklist = pd.DataFrame(
            {
                "Rule": [label for label, _ in checks],
                "Status": ["✅ Pass" if ok else "⚠️ Review" for _, ok in checks],
            }
        )
        st.dataframe(checklist, use_container_width=True, hide_index=True)

        if risk_reward < 2 or signal_strength < 7 or stop_pct > 8:
            st.warning("This setup needs extra caution for short-term trading. Reduce size, wait for a tighter entry, or skip.")
        else:
            st.success("Setup passes the basic short-term risk checks. Still confirm trend, liquidity, news, and your daily loss limit before trading.")
        st.caption("Discipline note: cap per-trade risk, define the stop before entry, and stop trading for the day after your preset daily loss limit.")

    with st.expander("🧮 Position Sizer", expanded=False):
        size_col_1, size_col_2, size_col_3 = st.columns(3)
        account = size_col_1.number_input("Account Size (₹)", 10_000, 10_000_000, 100_000, 10_000, key=f"acct_{ticker}")
        risk_pct = size_col_2.number_input("Risk per Trade (%)", 0.25, 5.0, 1.0, 0.25, key=f"rpct_{ticker}")
        daily_stop_pct = size_col_3.number_input("Daily Stop (%)", 0.5, 10.0, 3.0, 0.5, key=f"dstp_{ticker}")
        risk_amount = account * risk_pct / 100
        daily_stop_amount = account * daily_stop_pct / 100
        quantity = int(risk_amount // risk) if risk > 0 else 0
        position_value = quantity * entry
        metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
        metric_col_1.metric("Risk Amount", f"₹{risk_amount:,.0f}")
        metric_col_2.metric("Shares to Buy", quantity)
        metric_col_3.metric("Position Value", f"₹{position_value:,.0f}")
        metric_col_4.metric("Portfolio %", f"{position_value / account * 100:.1f}%")
        losing_trades_to_stop = int(daily_stop_amount // risk_amount) if risk_amount > 0 else 0
        st.caption(f"Daily stop budget: ₹{daily_stop_amount:,.0f}. At this size, about {losing_trades_to_stop} full-risk losing trade(s) reach the daily limit.")

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
                    rr_label(target_1),
                    rr_label(target_2),
                    rr_label(target_3),
                ],
            }
        )
        st.dataframe(exit_df, use_container_width=True, hide_index=True)

    with st.spinner(f"Loading chart for {ticker}…"):
        chart_period = "1y" if timeframe == "1d" else "60d"
        df_chart = load_ticker_history(ticker, period=chart_period, interval=timeframe)
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
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "displaylogo": False,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            },
        )
        if st.button("🖥️ View Full Screen Chart", key=f"fs_{ticker}", use_container_width=True):
            show_full_chart(fig)
    else:
        st.warning("Chart data unavailable for this ticker.")

    st.divider()
    wcol1, wcol2 = st.columns([1, 1])
    if isinstance(st.session_state.get("watchlist"), list):
        st.session_state.watchlist = {"Default": st.session_state.watchlist}
    elif not isinstance(st.session_state.get("watchlist"), dict):
        st.session_state.watchlist = {"Default": []}

    wl_target = wcol1.selectbox("Watchlist", options=list(st.session_state.watchlist.keys()), key=f"wl_sel_{ticker}")
    if wcol2.button("➕ Add to Watchlist", key=f"aw_{ticker}", use_container_width=True):
        if ticker not in st.session_state.watchlist[wl_target]:
            st.session_state.watchlist[wl_target].append(ticker)
            save_current_user_workspace()
            st.success(f"{ticker} added to '{wl_target}'")
        else:
            st.info(f"{ticker} is already in '{wl_target}'")

    return True


def _render_results_blotter(filtered_results: pd.DataFrame):
    display_columns = [
        "Ticker",
        "LTP",
        "Action",
        "Setup_Score",
        "Consol_Days",
        "Base_Weeks",
        "ROE",
        "Sector",
        "Sector_Score",
        "Mkt_Cap_Cr",
        "FII_Chg_%",
        "FII_Hold_%",
        "ROCE",
        "Profit_Growth_%",
        "Sales_Growth_%",
        "PE",
        "Pattern",
        "RS_Rating",
        "Vol_x",
        "Stop_%",
        "RR",
        "Risk_Grade",
        "Market_Health",
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
            "Stop_%": "Stop%",
            "Risk_Grade": "Risk",
            "Market_Health": "Breadth",
            "Mkt_Cap_Cr": "MktCap",
            "FII_Chg_%": "FII+",
            "FII_Hold_%": "FII%",
            "Profit_Growth_%": "Profit%",
            "Sales_Growth_%": "Sales%",
            "Vol_Spike": "Spike",
            "Type": "Level",
            "RS_Rating": "RS",
            "Sector_Score": "Sect.Score",
            "Base_Weeks": "Base",
            "Setup_Score": "Setup",
            "Consol_Days": "Tight Days",
        }
    ).copy()

    def _short_term_status(row):
        risk = str(row.get("Risk", "")).strip()
        breadth = str(row.get("Breadth", "")).strip()
        strength = float(row.get("Strength", 0) or 0)
        stop = float(row.get("Stop%", 999) or 999)
        if breadth == "Risk-Off" or risk == "Reduce/Skip" or stop > 8 or strength < 7:
            return "Caution"
        if risk in {"A", "B"} and breadth in {"Risk-On", "Constructive"} and stop <= 8 and strength >= 7:
            return "Ready"
        if risk == "C":
            return "Watch"
        return "Review"

    if {"Risk", "Breadth", "Strength", "Stop%"}.issubset(rendered_df.columns):
        rendered_df["Execution"] = rendered_df.apply(_short_term_status, axis=1)
        if "Breadth" in rendered_df.columns:
            cols = list(rendered_df.columns)
            cols.insert(cols.index("Breadth") + 1, cols.pop(cols.index("Execution")))
            rendered_df = rendered_df[cols]

    def highlight_high_sector(s):
        """Highlight rows where the Sector Score is 8.0 or higher."""
        is_high = "Sect.Score" in s.index and s["Sect.Score"] >= 8.0
        return ['background-color: rgba(0, 255, 170, 0.15)' if is_high else '' for _ in s]

    def highlight_long_term_bottom(s):
        """Highlight rows where the Pattern contains 'Base-20W' in gold."""
        is_base_20 = "Pattern" in s.index and "Base-20W" in str(s["Pattern"])
        return ['background-color: rgba(255, 215, 0, 0.25)' if is_base_20 else '' for _ in s]

    def highlight_setup_type(s):
        """Highlight rows based on the type of signal (VCP/Pre-Breakout vs Standard)."""
        action = str(s["Action"])
        if "VCP" in action:
            return ['background-color: rgba(139, 92, 246, 0.2)'] * len(s) # Purple tint for VCP
        if "Near" in action:
            return ['background-color: rgba(34, 211, 238, 0.15)'] * len(s) # Cyan tint for Near Breakout
        return ['' for _ in s]

    # Chain the sector highlight, long-term bottom (gold), and setup type highlights
    styled = style_scanner_results(rendered_df).apply(highlight_high_sector, axis=1).apply(highlight_long_term_bottom, axis=1).apply(highlight_setup_type, axis=1)

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
        results, stats, scan_time = scanner_service.fetch_cached_data(
            True,
            universe=settings.universe,
            scanner_type=settings.scanner_type,
            timeframe=settings.timeframe,
        )
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
        st.session_state.scan_running = True
        progress_bar = st.progress(0.0)
        progress_text = st.empty()

        def _progress(progress_value: float) -> None:
            progress_bar.progress(min(progress_value, 1.0))
            progress_text.markdown(
                f"<div style='color:#8899bb;font-size:0.8rem;font-family:JetBrains Mono;'>Scanning · {int(progress_value * 100)}%</div>",
                unsafe_allow_html=True,
            )

        try:
            with st.spinner("Downloading market data from Yahoo Finance…"):
                is_total_market = settings.universe == "Total Market (Cap Focused)"
                min_cap = settings.min_mkt_cap if is_total_market else 0
                max_cap = settings.max_mkt_cap if is_total_market else 0
                sector_map = get_sector_mapping(settings.universe)
                results, stats, scan_time = scanner_service.perform_fresh_scan(
                    universe=settings.universe,
                    vol_thresh=settings.vol_thresh,
                    rsi_min=settings.rsi_range[0],
                    rsi_max=settings.rsi_range[1],
                    dist_thresh=settings.dist_thresh,
                    min_mkt_cap_cr=min_cap,
                    max_mkt_cap_cr=max_cap,
                    scanner_type=settings.scanner_type,
                    timeframe=settings.timeframe,
                    sector_map=sector_map,
                    include_news_sentiment=settings.include_news,
                    progress_callback=_progress,
                )
        finally:
            progress_bar.empty()
            progress_text.empty()
            st.session_state.scan_running = False

        st.session_state.update(
            results=results,
            stats=stats,
            last_scan_time=scan_time.split(" ")[1] if " " in scan_time else scan_time,
            run_scan=False,
            scan_source="Live",
        )
        _maybe_send_scan_alerts(results, settings.scanner_type)
        status_placeholder.success(f"✅ Scan complete · {scan_time}")
    elif settings.use_cache and results is not None and not need_scan:
        status_placeholder.info("ℹ️ Showing previous results. Click Load Cached Scan to refresh from cache.")

    filtered_results = _apply_result_filters(results)

    if results is not None and len(results) > 0:
        _render_status_banner(
            results, filtered_results, st.session_state.last_scan_time,
            st.session_state.get("scan_source"), stats,
            timeframe=(stats or {}).get("timeframe", settings.timeframe),
        )
        focus_mode = bool(st.session_state.get("focus_mode", False))
        if not focus_mode and st.session_state.get("show_top_picks", True):
            render_top_picks(filtered_results if filtered_results is not None and len(filtered_results) > 0 else results)
        _render_metrics(results, stats, scan_time)
        if not focus_mode and st.session_state.get("show_macro_context", True):
            _render_macro_context(stats)
        _render_filter_breakdown(stats)
        if not focus_mode and st.session_state.get("show_watchlist_quick_add", True):
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
                            <div class="terminal-title" style="color: #00e5ff;">Signal Blotter</div>
                            <div class="terminal-subtitle" style="color: #94a3b8;">Ranked breakout candidates after post-scan filtering</div>
                        </div>
                        <div class="terminal-badge" style="background: #00e5ff; color: #000000; font-weight: bold; padding: 2px 8px; border-radius: 4px;">{len(filtered_results)} MATCHES</div>
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
                            <div class="terminal-title" style="color: #00e5ff;">Setup Workspace</div>
                            <div class="terminal-subtitle" style="color: #94a3b8;">Levels, confirmations, chart context, and sizing</div>
                        </div>
                        <div class="terminal-badge" style="background: #94a3b8; color: #000000; font-weight: bold; padding: 2px 8px; border-radius: 4px;">DETAIL</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )
            has_selection = _render_detail_view(filtered_results.reset_index(drop=True), selection, load_ticker_history, chart_options, settings.timeframe)
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
