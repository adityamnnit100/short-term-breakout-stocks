"""Scanner tab UI."""

from typing import Optional
import math

import pandas as pd
import streamlit as st
import uuid
import logging

from breakout_readiness import rank_breakout_readiness
from multi_timeframe import rank_multi_timeframe_candidates
import scanner_service
from alphascanner_ui.auth import save_current_user_workspace
from alphascanner_ui.charts import build_chart, style_scanner_results, plotly_config
from alphascanner_ui.data import get_sector_mapping
from alphascanner_ui.services.alerts_service import get_alerts_service

logger = logging.getLogger("AlphaScanner.UI.Scanner")


def _filter_chart_range(df: pd.DataFrame, selected_range: str) -> pd.DataFrame:
    """Return the candles for a user-selected chart range."""
    if df is None or df.empty or selected_range == "All":
        return df

    data = df.sort_index()
    latest = data.index.max()
    if selected_range == "1D":
        # 1D denotes candle interval: retain the full daily history so each
        # candle is one trading day rather than treating 1D as a date range.
        return data
    elif selected_range == "1M":
        start = latest - pd.DateOffset(months=1)
    elif selected_range == "YTD":
        start = pd.Timestamp(year=latest.year, month=1, day=1, tz=latest.tz)
    elif selected_range == "1Y":
        start = latest - pd.DateOffset(years=1)
    else:
        return data

    filtered = data.loc[data.index >= start]
    return filtered if not filtered.empty else data.tail(1)


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
    # prefer an explicitly set active theme for the full-chart (set by the caller),
    # otherwise fall back to the global/default chart theme
    theme = st.session_state.pop("active_full_chart_theme", st.session_state.get("chart_theme", "dark"))
    # Use a unique key to avoid StreamlitDuplicateElementId when multiple charts render
    unique_key = f"full_chart_{uuid.uuid4().hex}"
    st.plotly_chart(
        fig,
        use_container_width=True,
        config=plotly_config(theme),
        key=unique_key,
    )


def _apply_result_filters(results: pd.DataFrame) -> pd.DataFrame:
    if results is None or results.empty:
        return results

    modular_results = _is_modular_results(results)

    with st.expander("Post-Scan Filters", expanded=False):
        fcol1, fcol2, fcol3, fcol4, fcol5, fcol6, fcol7, fcol8 = st.columns(8)
        if modular_results:
            score_column = "Watchlist Score" if "Watchlist Score" in results.columns else "Entry Score"
            min_score = fcol1.slider(
                "Min Score",
                0.0,
                100.0,
                float(st.session_state.get("filter_min_modular_score", 0.0)),
                0.5,
                key="filter_min_modular_score",
            )
            quality_choices = fcol2.multiselect(
                "Trade Quality",
                ["A+", "A", "B", "C", "Reject"],
                default=st.session_state.get("filter_trade_quality", ["A+", "A", "B", "C", "Reject"]),
                key="filter_trade_quality",
            ) if "Trade Quality" in results.columns else None
            recommendation_choices = fcol3.multiselect(
                "Recommendation",
                ["Buy", "Watch Closely", "Watch", "Reject"],
                default=st.session_state.get("filter_recommendation", ["Buy", "Watch Closely", "Watch", "Reject"]),
                key="filter_recommendation",
            ) if "Recommendation" in results.columns else None
            sector_choices = fcol4.multiselect(
                "Sector",
                sorted(results["Sector"].dropna().astype(str).unique().tolist()) if "Sector" in results.columns else [],
                default=st.session_state.get("filter_sector", []),
                key="filter_sector",
            ) if "Sector" in results.columns else None
            # keep the remaining columns empty to preserve the 8-column layout
            min_rsi = min_vol = min_base = max_stop = risk_choices = breadth_choices = execution_choices = None
        else:
            min_strength = fcol1.slider("Min Strength", 0, 10, st.session_state.get("filter_min_strength", 1), key="filter_min_strength")
            min_rsi = fcol2.slider("Min RSI", 0, 100, st.session_state.get("filter_min_rsi", 50), key="filter_min_rsi") if "RSI" in results.columns else None
            min_vol = fcol3.slider("Min Volume ×", 1.0, 5.0, st.session_state.get("filter_min_vol", 1.0), key="filter_min_vol") if "Vol_x" in results.columns else None
            min_base = fcol4.slider("Min Base (Weeks)", 0, 20, st.session_state.get("filter_min_base", 0), key="filter_min_base") if "Base_Weeks" in results.columns else None
            max_stop = fcol5.slider("Max Stop %", 1.0, 15.0, st.session_state.get("filter_max_stop", 8.0), 0.5, key="filter_max_stop") if "Stop_%" in results.columns else None
            risk_choices = fcol6.multiselect(
                "Risk Grade",
                ["A", "B", "C", "Reduce/Skip"],
                default=st.session_state.get("filter_risk_choices", ["A", "B", "C"]),
                key="filter_risk_choices",
            ) if "Risk_Grade" in results.columns else None
            breadth_choices = fcol7.multiselect(
                "Breadth",
                ["Any", "Risk-On", "Constructive", "Caution", "Risk-Off"],
                default=st.session_state.get("filter_breadth_choices", ["Any"]),
                key="filter_breadth_choices",
            ) if "Market_Health" in results.columns else None
            execution_choices = fcol8.multiselect(
                "Execution",
                ["Any", "Ready", "Caution", "Watch", "Review"],
                default=st.session_state.get("filter_execution_choices", ["Any"]),
                key="filter_execution_choices",
            ) if {"Risk_Grade", "Market_Health", "Signal_Strength", "Stop_%"}.issubset(results.columns) else None

    if modular_results:
        mask = pd.to_numeric(results[score_column], errors="coerce").fillna(0) >= min_score
        if quality_choices:
            mask &= results["Trade Quality"].isin(quality_choices)
        if recommendation_choices:
            mask &= results["Recommendation"].isin(recommendation_choices)
        if sector_choices:
            mask &= results["Sector"].isin(sector_choices)
    else:
        # guard: if Signal_Strength missing, treat as zeros so filters still work
        if "Signal_Strength" in results.columns:
            base_strength = results["Signal_Strength"]
        else:
            base_strength = pd.Series(0, index=results.index)

        mask = base_strength >= min_strength

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
    scan_mode: Optional[str] = None,
) -> None:
    total_results = 0 if results is None else len(results)
    filtered_count = 0 if filtered_results is None else len(filtered_results)
    source_label = scan_source or "None"
    time_label = scan_time or "Never"
    timeframe_label = "Daily" if timeframe == "1d" else (timeframe or "Daily")
    scan_mode_label = scan_mode or "Modular Scan"

    trending = (stats or {}).get("trending_sectors", [])
    sector_scores = (stats or {}).get("sector_sentiment", {})

    pills = ""
    for s in trending:
        score = sector_scores.get(s, 5.0)
        color = "#00ffaa" if score >= 8 else ("#ffca28" if score >= 5 else "#ff5252")
        pills += f'<span class="mini-tag" style="background:rgba(0,0,0,0.3); color:{color}; border:1px solid {color}66; margin-top:4px; display:inline-block;">{s} ({score})</span>'

    market_health = (stats or {}).get("market_health", "Unknown")
    sector_section = f'<div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(128,128,128,0.2);"><div class="status-label" style="margin-bottom:6px; color:#94a3b8;">🔥 Outperforming Sectors (vs Nifty)</div><div style="display:flex; flex-wrap:wrap; gap:6px;">{pills if pills else "No trending sectors detected"}</div></div>'

    st.markdown(
        f'<div class="glass-card" style="margin: 8px 0 18px;">'
        f'<div class="panel-title" style="color: #00e5ff;">Scanner Status</div>'
        f'<div class="status-grid">'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Source</div><div class="status-value" style="color: #00e5ff;">{source_label}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Timeframe</div><div class="status-value" style="color: #00e5ff;">{timeframe_label}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Total Results</div><div class="status-value" style="color: #00e5ff;">{total_results}</div></div>'
        f'<div class="status-cell"><div class="status-label" style="color: #94a3b8;">Market Breadth</div><div class="status-value" style="color: #00e5ff;">{market_health}</div></div>'
        f'</div>'
        f'<div style="margin-top:8px;color:#64748b;font-size:0.82rem;">Last run: {time_label} · Mode: {scan_mode_label} · Visible after filters: {filtered_count}</div>'
        f'{sector_section}</div>',
        unsafe_allow_html=True,
    )

    diagnostics_text = (stats or {}).get("diagnostics_summary_text")
    if diagnostics_text:
        with st.expander("Scanner Diagnostics", expanded=False):
            st.text(diagnostics_text)


def _render_metrics(results: pd.DataFrame, stats: Optional[dict], scan_time: Optional[str]) -> None:
    total_hits = len(results)
    scanned = (stats or {}).get("scanned", 0)
    universe_size = (stats or {}).get("universe_size") or scanned
    universe_label = (stats or {}).get("universe") or "Universe"
    modular_results = _is_modular_results(results)
    if modular_results:
        score_col = "Watchlist Score" if "Watchlist Score" in results.columns else "Entry Score"
        avg_score = pd.to_numeric(results[score_col], errors="coerce").mean() if score_col in results.columns else 0
        top_quality = results["Trade Quality"].value_counts().idxmax() if "Trade Quality" in results.columns and not results["Trade Quality"].empty else "N/A"
        primary_label = "Avg Score"
        primary_value = f"{avg_score:.0f}"
        primary_color = "#00e676" if avg_score >= 80 else "#ffca28" if avg_score >= 60 else "#f97316"
        primary_delta = "score quality"
        secondary_label = "Top Quality"
        secondary_value = top_quality
        secondary_delta = "best ranked setup"
    else:
        avg_rsi = results["RSI"].mean() if "RSI" in results else 0
        avg_strength = results["Signal_Strength"].mean() if "Signal_Strength" in results else 0
        primary_label = "Avg RSI"
        primary_value = f"{avg_rsi:.0f}"
        primary_color = "#ffca28" if avg_rsi > 70 else "#00e676"
        primary_delta = "momentum zone"
        secondary_label = "Avg Strength"
        secondary_value = f"{avg_strength:.1f}/10"
        secondary_delta = "Strong" if avg_strength >= 6 else "Moderate"
    pass_rate = total_hits / max(scanned, 1) * 100

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
        f'<div class="metric-label" style="color: #94a3b8;">{primary_label}</div>'
        f'<div class="metric-value" style="color:{primary_color};">{primary_value}</div>'
        f'<div class="metric-delta neutral" style="color: #64748b;">{primary_delta}</div></div>'
        f'<div class="metric-card">'
        f'<div class="metric-label" style="color: #94a3b8;">{secondary_label}</div>'
        f'<div class="metric-value" style="color: #00e5ff;">{secondary_value}</div>'
        f'<div class="metric-delta {"neutral" if modular_results else ("up" if avg_strength >= 6 else "down")}">{secondary_delta}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


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

    # Chart display is separate from the scanner's analysis interval. Here 1D
    # means daily candles across historical data, not a one-day viewing window.
    tcol1, tcol2 = st.columns([1, 3])
    theme_key = f"chart_theme_{ticker}"
    with tcol1:
        st.session_state.setdefault(theme_key, "dark")
        default_idx = 0 if st.session_state.get(theme_key, "dark") == "dark" else 1
        theme_choice = st.selectbox("Chart theme", ["dark", "light"], index=default_idx, key=theme_key, help="Choose chart theme for this chart")
    with tcol2:
        chart_range = st.radio(
            "Chart range",
            ["1D", "1M", "YTD", "1Y", "All"],
            horizontal=True,
            key=f"chart_range_{ticker}",
        )

    period_interval = {
        "1D": ("1y", "1d"),
        "1M": ("1mo", "1d"),
        "YTD": ("ytd", "1d"),
        "1Y": ("1y", "1d"),
        "All": ("5y", "1d"),
    }
    chart_period, chart_interval = period_interval[chart_range]
    with st.spinner(f"Loading {chart_range} chart for {ticker}…"):
        df_chart = load_ticker_history(ticker, period=chart_period, interval=chart_interval)

    last_err = st.session_state.get("last_data_error")
    if last_err:
        st.error(f"Chart data error: {last_err}")

    if not df_chart.empty:
        df_chart_view = _filter_chart_range(df_chart, chart_range)
        fig = build_chart(
            df_chart_view,
            ticker,
            row,
            show_sma=chart_options.show_sma,
            show_ema=chart_options.show_ema,
            show_bb=chart_options.show_bb,
            show_rsi=chart_options.show_rsi,
            show_macd=chart_options.show_macd,
            show_vwap=chart_options.show_vwap,
            theme=theme_choice,
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            config=plotly_config(theme_choice),
            key=f"chart_v5_{ticker}_{chart_range}_{chart_interval}",
        )
        if st.button("🖥️ View Full Screen Chart", key=f"fs_{ticker}", use_container_width=True):
            # record the active theme for the full-screen dialog and open it
            st.session_state["active_full_chart_theme"] = theme_choice
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


def _render_results_blotter(filtered_results: pd.DataFrame, use_rich_style: bool = True):
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

    if use_rich_style:
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

    return st.dataframe(
        rendered_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )


def _is_modular_results(results: pd.DataFrame) -> bool:
    if results is None or results.empty:
        return False
    return "Watchlist Score" in results.columns or "Entry Score" in results.columns


def _results_signature(results: pd.DataFrame, stats: Optional[dict], scan_time: Optional[str]) -> str:
    if results is None or results.empty:
        return "empty"
    head = tuple(str(x) for x in results.get("Ticker", pd.Series(dtype=str)).head(3).tolist())
    tail = tuple(str(x) for x in results.get("Ticker", pd.Series(dtype=str)).tail(3).tolist())
    return "|".join(
        [
            str(len(results)),
            str((stats or {}).get("scanned", len(results))),
            str((stats or {}).get("universe", "")),
            str((stats or {}).get("timeframe", "")),
            str(scan_time or ""),
            ",".join(head),
            ",".join(tail),
        ]
    )


def _get_cached_breakout_readiness(results: pd.DataFrame, load_ticker_history, load_nifty_history) -> pd.DataFrame:
    if results is None or results.empty or "Ticker" not in results.columns:
        return pd.DataFrame()

    cache_key = _results_signature(results, st.session_state.get("stats"), st.session_state.get("last_scan_time"))
    cached_key = st.session_state.get("breakout_readiness_cache_key")
    cached_frame = st.session_state.get("breakout_readiness_cache")
    if cached_key == cache_key and isinstance(cached_frame, pd.DataFrame):
        return cached_frame

    readiness = rank_breakout_readiness(
        results,
        history_loader=load_ticker_history,
        benchmark_loader=load_nifty_history,
        max_candidates=min(8, len(results)),
        min_score=45.0,
    )
    if readiness is None:
        readiness = pd.DataFrame()

    st.session_state["breakout_readiness_cache_key"] = cache_key
    st.session_state["breakout_readiness_cache"] = readiness
    return readiness


def _paginate_results(results: pd.DataFrame, page_size: int, page: int) -> tuple:
    if results is None or results.empty:
        return results, 1, 1

    page_size = max(1, int(page_size or 20))
    total_pages = max(1, math.ceil(len(results) / page_size))
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return results.iloc[start:end].copy(), page, total_pages


def _scanner_pager_key(settings) -> str:
    scanner_type = str(getattr(settings, "scanner_type", "scanner")).replace(" ", "_").lower()
    scan_mode = str(getattr(settings, "scan_mode", "")).replace(" ", "_").lower()
    universe = str(getattr(settings, "universe", "")).replace(" ", "_").lower()
    timeframe = str(getattr(settings, "timeframe", "")).replace(" ", "_").lower()
    return f"scanner_blotter_{scanner_type}_{scan_mode}_{universe}_{timeframe}"


def _scanner_detail_key(settings) -> str:
    return f"{_scanner_pager_key(settings)}_detail_ticker"


def _scanner_detail_suppress_key(settings) -> str:
    return f"{_scanner_pager_key(settings)}_detail_suppress_ticker"


def _selection_to_ticker(results: pd.DataFrame, selection) -> Optional[str]:
    if results is None or results.empty or not isinstance(selection, dict):
        return None
    selected_rows = selection.get("selection", {}).get("rows", [])
    if not selected_rows:
        return None
    row_idx = selected_rows[0]
    if row_idx < 0 or row_idx >= len(results):
        return None
    ticker = str(results.iloc[row_idx].get("Ticker", "")).strip()
    return ticker or None


def _render_modular_results_blotter(filtered_results: pd.DataFrame):
    if filtered_results is None or filtered_results.empty:
        return None

    if "Watchlist Score" in filtered_results.columns:
        display_columns = [
            "Ticker",
            "Watchlist Score",
            "Sector",
            "Trend",
            "Base Score",
            "Volume Score",
            "Relative Strength",
            "ATR Contraction",
            "Days in Consolidation",
            "Trade Quality",
            "Setup ID",
            "Transition Score",
            "Transition Category",
            "Trigger Decision",
            "Trigger Confidence",
            "Recommendation",
        ]
    else:
        display_columns = [
            "Ticker",
            "Entry Score",
            "Sector",
            "Entry Price",
            "Stop Loss",
            "Risk %",
            "Target 1",
            "Target 2",
            "Risk Reward",
            "Breakout Date",
            "Breakout Volume Ratio",
            "Trade Quality",
            "Setup ID",
            "Transition Score",
            "Transition Category",
            "Trigger Decision",
            "Trigger Confidence",
            "Recommendation",
        ]

    available_columns = [column for column in display_columns if column in filtered_results.columns]
    rendered_df = filtered_results[available_columns].copy()

    try:
        return st.dataframe(
            rendered_df,
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


def _render_breakout_readiness_panel(results: pd.DataFrame, load_ticker_history, load_nifty_history, nested: bool = False) -> None:
    if results is None or results.empty or "Ticker" not in results.columns:
        return

    readiness = _get_cached_breakout_readiness(results, load_ticker_history, load_nifty_history)
    if readiness is None or readiness.empty:
        return

    display_cols = [
        "ticker",
        "breakout_readiness_score",
        "current_price",
        "nearest_resistance",
        "resistance_gap_pct",
        "compression_score",
        "breakout_distance_score",
        "volume_dryup_score",
        "candle_tightness_score",
        "rs_acceleration_score",
        "breakout_pressure_score",
        "confluence_bonus",
        "sector",
        "reasons",
    ]
    rendered = readiness[[col for col in display_cols if col in readiness.columns]].rename(
        columns={
            "ticker": "Ticker",
            "breakout_readiness_score": "Readiness Score",
            "current_price": "Price",
            "nearest_resistance": "Resistance",
            "resistance_gap_pct": "Gap %",
            "compression_score": "Compression",
            "breakout_distance_score": "Distance",
            "volume_dryup_score": "Volume Dry-up",
            "candle_tightness_score": "Candle Tightness",
            "rs_acceleration_score": "RS Accel",
            "breakout_pressure_score": "Pressure",
            "confluence_bonus": "Bonus",
            "sector": "Sector",
            "reasons": "Why",
        }
    )

    if nested:
        st.markdown("#### Breakout Readiness Engine")
        st.caption("This ranks the current scanner output again and keeps only the strongest imminent-breakout candidates.")
        st.dataframe(rendered, use_container_width=True, hide_index=True)
        return

    with st.expander("Breakout Readiness Engine", expanded=True):
        st.caption("This ranks the current scanner output again and keeps only the strongest imminent-breakout candidates.")
        st.dataframe(rendered, use_container_width=True, hide_index=True)


def _render_multi_timeframe_panel(results: pd.DataFrame, load_ticker_history, regime_result: dict, settings, nested: bool = False) -> None:
    if results is None or results.empty or not getattr(settings, "enable_multi_timeframe_confirmation", False):
        return

    try:
        ranking = rank_multi_timeframe_candidates(
            results,
            history_loader=load_ticker_history,
            regime_result=regime_result,
            config=None,
            max_candidates=min(8, len(results)),
        )
    except Exception:
        return
    if ranking is None or ranking.empty:
        return

    display_cols = [
        "Ticker",
        "Weekly Score",
        "Daily Score",
        "1H Score",
        "Raw Score",
        "Final Score",
        "Weekly State",
        "Market Regime",
        "Recommendation",
        "Sector",
    ]
    rendered = ranking[[col for col in display_cols if col in ranking.columns]].copy()
    if nested:
        st.markdown("#### Multi-Timeframe Confirmation Engine")
        st.caption("Weekly trend has veto power. This panel is intentionally optional until you are satisfied with the regime filter.")
        st.dataframe(rendered, use_container_width=True, hide_index=True)
        return

    with st.expander("Multi-Timeframe Confirmation Engine", expanded=True):
        st.caption("Weekly trend has veto power. This panel is intentionally optional until you are satisfied with the regime filter.")
        st.dataframe(rendered, use_container_width=True, hide_index=True)


def _render_modular_detail_view(results, selection, load_ticker_history, chart_options, timeframe: str = "1d") -> bool:
    selected_rows = selection.get("selection", {}).get("rows", [])
    if not selected_rows:
        return False

    row = results.iloc[selected_rows[0]].to_dict()
    ticker = row.get("Ticker", "")
    if not ticker:
        return False

    score_label = "Watchlist Score" if "Watchlist Score" in row else "Entry Score"
    score_value = row.get(score_label, 0)
    recommendation = row.get("Recommendation", "")
    quality = row.get("Trade Quality", "")
    setup_id = row.get("Setup ID", "")
    setup_score = row.get("Setup Score", "")
    setup_category = row.get("Setup Category", "")
    transition_score = row.get("Transition Score", "")
    transition_category = row.get("Transition Category", "")
    trigger_decision = row.get("Trigger Decision", "")
    trigger_confidence = row.get("Trigger Confidence", "")
    reason_text = row.get("Reason Text", "")
    sector = row.get("Sector", "Unknown")
    trend = row.get("Trend", "")

    st.markdown(
        f'<div class="glass-card" style="margin-bottom: 12px; padding: 16px;">'
        f'<div class="panel-title" style="color: #00e5ff;">{ticker} — {score_label}</div>'
        f'<div style="color: #94a3b8; margin-bottom: 10px;">Mode: {"Watchlist" if score_label == "Watchlist Score" else "Entry"} · Recommendation: {recommendation} · Quality: {quality} · Setup: {setup_id} · Setup Score: {setup_score} · Category: {setup_category} · Transition Score: {transition_score} · Transition Category: {transition_category} · Trigger: {trigger_decision} · Confidence: {trigger_confidence}</div>'
        f'<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;">'
        f'<div><div class="metric-label">Score</div><div class="metric-value">{score_value}</div></div>'
        f'<div><div class="metric-label">Sector</div><div class="metric-value">{sector}</div></div>'
        f'<div><div class="metric-label">Trend</div><div class="metric-value">{trend}</div></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if score_label == "Watchlist Score":
        st.markdown(
            f'<div class="glass-card" style="margin-bottom: 12px; padding: 16px;">'
            f'<div class="panel-title" style="color: #00e5ff;">Watchlist Context</div>'
            f'<div><b>Base Score:</b> {row.get("Base Score", "-")}</div>'
            f'<div><b>Volume Score:</b> {row.get("Volume Score", "-")}</div>'
            f'<div><b>Relative Strength:</b> {row.get("Relative Strength", "-")}</div>'
            f'<div><b>ATR Contraction:</b> {row.get("ATR Contraction", "-")}</div>'
            f'<div><b>Days in Consolidation:</b> {row.get("Days in Consolidation", "-")}</div>'
            f'<hr style="opacity:0.2;"/><div><b>Setup Base:</b> {row.get("Setup Base Score", "-")}</div>'
            f'<div><b>Setup Compression:</b> {row.get("Setup Compression Score", "-")}</div>'
            f'<div><b>Setup Volume:</b> {row.get("Setup Volume Score", "-")}</div>'
            f'<div><b>Setup Resistance:</b> {row.get("Setup Resistance Score", "-")}</div>'
            f'<div><b>Setup Structure:</b> {row.get("Setup Structure Score", "-")}</div>'
            f'<div><b>Setup Risk:</b> {row.get("Setup Risk Score", "-")}</div>'
            f'<hr style="opacity:0.2;"/><div><b>Transition Score:</b> {row.get("Transition Score", "-")}</div>'
            f'<div><b>Transition Category:</b> {row.get("Transition Category", "-")}</div>'
            f'<div><b>Transition Setup Velocity:</b> {row.get("Transition Setup Velocity Score", "-")}</div>'
            f'<div><b>Transition RS Acceleration:</b> {row.get("Transition RS Acceleration Score", "-")}</div>'
            f'<div><b>Transition Volume:</b> {row.get("Transition Volume Score", "-")}</div>'
            f'<div><b>Transition Compression:</b> {row.get("Transition Compression Score", "-")}</div>'
            f'<div><b>Transition Resistance:</b> {row.get("Transition Resistance Score", "-")}</div>'
            f'<div><b>Transition Price Acceptance:</b> {row.get("Transition Price Acceptance Score", "-")}</div>'
            f'<div><b>Transition Opportunity Velocity:</b> {row.get("Transition Opportunity Velocity Score", "-")}</div>'
            f'<hr style="opacity:0.2;"/><div><b>Trigger Decision:</b> {row.get("Trigger Decision", "-")}</div>'
            f'<div><b>Trigger Confidence:</b> {row.get("Trigger Confidence", "-")}</div>'
            f'<div><b>Trigger Passed Modules:</b> {row.get("Trigger Passed Modules", "-")}</div>'
            f'<div><b>Trigger Failed Modules:</b> {row.get("Trigger Failed Modules", "-")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="glass-card" style="margin-bottom: 12px; padding: 16px;">'
            f'<div class="panel-title" style="color: #00e5ff;">Entry Context</div>'
            f'<div><b>Entry Price:</b> {row.get("Entry Price", "-")}</div>'
            f'<div><b>Stop Loss:</b> {row.get("Stop Loss", "-")}</div>'
            f'<div><b>Risk %:</b> {row.get("Risk %", "-")}</div>'
            f'<div><b>Targets:</b> {row.get("Target 1", "-")} / {row.get("Target 2", "-")}</div>'
            f'<div><b>Breakout Volume Ratio:</b> {row.get("Breakout Volume Ratio", "-")}</div>'
            f'<hr style="opacity:0.2;"/><div><b>Setup Base:</b> {row.get("Setup Base Score", "-")}</div>'
            f'<div><b>Setup Compression:</b> {row.get("Setup Compression Score", "-")}</div>'
            f'<div><b>Setup Volume:</b> {row.get("Setup Volume Score", "-")}</div>'
            f'<div><b>Setup Resistance:</b> {row.get("Setup Resistance Score", "-")}</div>'
            f'<div><b>Setup Structure:</b> {row.get("Setup Structure Score", "-")}</div>'
            f'<div><b>Setup Risk:</b> {row.get("Setup Risk Score", "-")}</div>'
            f'<hr style="opacity:0.2;"/><div><b>Transition Score:</b> {row.get("Transition Score", "-")}</div>'
            f'<div><b>Transition Category:</b> {row.get("Transition Category", "-")}</div>'
            f'<div><b>Transition Setup Velocity:</b> {row.get("Transition Setup Velocity Score", "-")}</div>'
            f'<div><b>Transition RS Acceleration:</b> {row.get("Transition RS Acceleration Score", "-")}</div>'
            f'<div><b>Transition Volume:</b> {row.get("Transition Volume Score", "-")}</div>'
            f'<div><b>Transition Compression:</b> {row.get("Transition Compression Score", "-")}</div>'
            f'<div><b>Transition Resistance:</b> {row.get("Transition Resistance Score", "-")}</div>'
            f'<div><b>Transition Price Acceptance:</b> {row.get("Transition Price Acceptance Score", "-")}</div>'
            f'<div><b>Transition Opportunity Velocity:</b> {row.get("Transition Opportunity Velocity Score", "-")}</div>'
            f'<hr style="opacity:0.2;"/><div><b>Trigger Decision:</b> {row.get("Trigger Decision", "-")}</div>'
            f'<div><b>Trigger Confidence:</b> {row.get("Trigger Confidence", "-")}</div>'
            f'<div><b>Trigger Passed Modules:</b> {row.get("Trigger Passed Modules", "-")}</div>'
            f'<div><b>Trigger Failed Modules:</b> {row.get("Trigger Failed Modules", "-")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if reason_text:
        st.expander("Why this candidate passed", expanded=False).write(reason_text)

    transition_reasons = row.get("Transition Reasons", [])
    transition_weaknesses = row.get("Transition Weaknesses", [])
    if transition_reasons or transition_weaknesses:
        with st.expander("Transition Notes", expanded=False):
            if transition_reasons:
                st.markdown("**Reasons**")
                for reason in transition_reasons if isinstance(transition_reasons, list) else [transition_reasons]:
                    st.write(f"✔ {reason}")
            if transition_weaknesses:
                st.markdown("**Weaknesses**")
                for weakness in transition_weaknesses if isinstance(transition_weaknesses, list) else [transition_weaknesses]:
                    st.write(f"⚠ {weakness}")

    trigger_reasons = row.get("Trigger Reasons", [])
    trigger_weaknesses = row.get("Trigger Weaknesses", [])
    trigger_modules = row.get("Trigger Passed Modules", [])
    if trigger_reasons or trigger_weaknesses or trigger_modules:
        with st.expander("Trigger Notes", expanded=False):
            if trigger_reasons:
                st.markdown("**Reasons**")
                for reason in trigger_reasons if isinstance(trigger_reasons, list) else [trigger_reasons]:
                    st.write(f"✔ {reason}")
            if trigger_weaknesses:
                st.markdown("**Weaknesses**")
                for weakness in trigger_weaknesses if isinstance(trigger_weaknesses, list) else [trigger_weaknesses]:
                    st.write(f"⚠ {weakness}")
            if trigger_modules:
                st.markdown("**Passed Modules**")
                for module in trigger_modules if isinstance(trigger_modules, list) else [trigger_modules]:
                    st.write(f"• {module}")

    return True


def render_tab(settings, chart_options, load_ticker_history, load_nifty_history, fetch_indices_performance) -> None:
    logger.debug(
        "render_tab(scan_type=%s, universe=%s, scan_mode=%s, timeframe=%s, use_cache=%s, run_scan=%s)",
        settings.scanner_type,
        settings.universe,
        settings.scan_mode,
        settings.timeframe,
        settings.use_cache,
        st.session_state.get("run_scan", False),
    )
    results = st.session_state.results
    stats = st.session_state.stats
    scan_time = st.session_state.last_scan_time
    need_scan = st.session_state.get("run_scan", False)
    status_placeholder = st.empty()

    # Chart theme selector moved to the per-ticker detail view (near the chart)

    if settings.use_cache and need_scan:
        results, stats, scan_time = scanner_service.fetch_cached_data(
            True,
            universe=settings.universe,
            scanner_type=settings.scanner_type,
            timeframe=settings.timeframe,
            scan_mode=settings.scan_mode,
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

    if not need_scan and results is None:
        status_placeholder.info("No scan loaded yet. Click Run Fresh Scan to start a modular scan.")
        return

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
                logger.debug(
                    "Starting fresh scan with min_cap=%s max_cap=%s sector_map_size=%s",
                    min_cap,
                    max_cap,
                    len(sector_map) if isinstance(sector_map, dict) else 0,
                )
                results, stats, scan_time = scanner_service.perform_fresh_scan(
                    universe=settings.universe,
                    vol_thresh=settings.vol_thresh,
                    rsi_min=settings.rsi_range[0],
                    rsi_max=settings.rsi_range[1],
                    dist_thresh=settings.dist_thresh,
                    min_mkt_cap_cr=min_cap,
                    max_mkt_cap_cr=max_cap,
                    scanner_type=settings.scanner_type,
                    scan_mode=settings.scan_mode,
                    timeframe=settings.timeframe,
                    sector_map=sector_map,
                    include_news_sentiment=settings.include_news,
                    progress_callback=_progress,
                    use_cache=settings.use_cache,
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

    if results is not None and len(results) == 0:
        pager_key = _scanner_pager_key(settings)
        st.session_state.pop(f"{pager_key}_page", None)
        st.session_state.pop(f"{pager_key}_page_size", None)
        st.info("No high-conviction opportunities match current scan parameters.", icon="ℹ️")
        return

    if results is not None and len(results) > 0:
        _render_status_banner(
            results, filtered_results, st.session_state.last_scan_time,
            st.session_state.get("scan_source"), stats,
            timeframe=(stats or {}).get("timeframe", settings.timeframe),
            scan_mode=settings.scan_mode,
        )
        if filtered_results is not None and len(filtered_results) == 0:
            st.warning("Your current post-scan filters hide all results. Relax Min Strength, RSI, or Volume × to see matches.")
            return

        pager_key = _scanner_pager_key(settings)
        page_size_key = f"{pager_key}_page_size"
        page_key = f"{pager_key}_page"
        page_sizes = [10, 20, 30, 50]
        if page_size_key not in st.session_state or int(st.session_state.get(page_size_key, 20) or 20) not in page_sizes:
            st.session_state[page_size_key] = 20
        blotter_page = int(st.session_state.get(page_key, 1) or 1)
        page_size = int(st.session_state.get(page_size_key, 20) or 20)
        page_results, blotter_page, total_pages = _paginate_results(filtered_results, page_size, blotter_page)
        st.session_state[page_key] = blotter_page

        detail_key = _scanner_detail_key(settings)
        suppress_key = _scanner_detail_suppress_key(settings)
        selected_detail_ticker = st.session_state.get(detail_key)

        filtered_lookup = {
            str(row.get("Ticker", "")).strip(): idx
            for idx, row in filtered_results.reset_index(drop=True).iterrows()
        }

        if selected_detail_ticker and selected_detail_ticker not in filtered_lookup:
            st.session_state.pop(detail_key, None)
            st.session_state.pop(suppress_key, None)
            selected_detail_ticker = None

        if selected_detail_ticker:
            detail_results = filtered_results.reset_index(drop=True)
            detail_index = filtered_lookup.get(selected_detail_ticker)
            if detail_index is not None:
                detail_selection = {"selection": {"rows": [detail_index]}}
                selected_row = detail_results.iloc[detail_index].to_dict()
                selected_label = str(selected_row.get("Ticker", selected_detail_ticker)).strip() or selected_detail_ticker
                breadcrumb_left, breadcrumb_right = st.columns([0.24, 0.76])
                with breadcrumb_left:
                    if st.button("← Signal Blotter", use_container_width=True, key=f"{detail_key}_back"):
                        st.session_state.pop(detail_key, None)
                        st.session_state[suppress_key] = selected_detail_ticker
                        st.rerun()
                with breadcrumb_right:
                    st.markdown(
                        f"""
                        <div style="padding: 0.35rem 0 0.15rem; color:#64748b; font-size:0.82rem; letter-spacing:0.04em;">
                            Scanner <span style="color:#94a3b8;">/</span>
                            <span style="color:#00e5ff; font-weight:600;">Signal Blotter</span> <span style="color:#94a3b8;">/</span>
                            <span style="color:#00e5ff; font-weight:600;">{selected_label}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.markdown(
                    f"""
                    <div class="terminal-panel">
                        <div class="terminal-head" style="margin-bottom: 8px;">
                            <div>
                                <div class="terminal-title" style="color: #00e5ff;">Setup Workspace</div>
                                <div class="terminal-subtitle" style="color: #94a3b8; margin-top: 2px;">Levels, confirmations, chart context, and sizing</div>
                            </div>
                            <div class="terminal-badge" style="background: #94a3b8; color: #000000; font-weight: bold; padding: 2px 8px; border-radius: 4px;">DETAIL</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if _is_modular_results(detail_results):
                    _render_modular_detail_view(detail_results, detail_selection, load_ticker_history, chart_options, settings.timeframe)
                else:
                    _render_detail_view(detail_results, detail_selection, load_ticker_history, chart_options, settings.timeframe)
            else:
                st.session_state.pop(detail_key, None)
                st.session_state.pop(suppress_key, None)
                selected_detail_ticker = None

        if not selected_detail_ticker:
            st.markdown(
                f"""
                <div class="terminal-panel">
                    <div class="terminal-head">
                        <div>
                            <div class="terminal-title" style="color: #00e5ff;">Signal Blotter</div>
                            <div class="terminal-subtitle" style="color: #94a3b8;">Ranked candidates after post-scan filtering</div>
                            <div style="display:inline-flex;align-items:center;gap:6px;margin-top:6px;padding:4px 10px;border-radius:999px;border:1px solid rgba(0,229,255,0.22);background:rgba(0,229,255,0.08);color:#00e5ff;font-size:0.78rem;font-weight:600;">
                                <span>↳</span><span>Click any row to open the detail page</span>
                            </div>
                        </div>
                        <div class="terminal-badge" style="background: #00e5ff; color: #000000; font-weight: bold; padding: 2px 8px; border-radius: 4px;">{len(filtered_results)} MATCHES</div>
                    </div>
                """,
                unsafe_allow_html=True,
            )
            if _is_modular_results(page_results):
                selection = _render_modular_results_blotter(page_results)
            else:
                use_rich_style = len(page_results) <= 120
                selection = _render_results_blotter(page_results, use_rich_style=use_rich_style)
            st.markdown("</div>", unsafe_allow_html=True)

            clicked_ticker = _selection_to_ticker(page_results.reset_index(drop=True), selection)
            suppressed_ticker = st.session_state.get(suppress_key)
            if clicked_ticker and clicked_ticker != suppressed_ticker:
                st.session_state[detail_key] = clicked_ticker
                st.session_state.pop(suppress_key, None)
                st.rerun()

            pager_col_1, pager_col_2, pager_col_3, pager_col_4 = st.columns([1.5, 0.75, 0.75, 2.0])
            with pager_col_1:
                page_size = int(st.selectbox("Rows / page", page_sizes, key=page_size_key))
            with pager_col_2:
                if st.button("◀ Prev", use_container_width=True, disabled=blotter_page <= 1):
                    st.session_state[page_key] = max(1, blotter_page - 1)
                    st.rerun()
            with pager_col_3:
                if st.button("Next ▶", use_container_width=True, disabled=blotter_page >= total_pages):
                    st.session_state[page_key] = min(total_pages, blotter_page + 1)
                    st.rerun()
            with pager_col_4:
                st.markdown(
                    f"<div style='padding-top: 0.45rem; color:#64748b; font-size:0.9rem; text-align:right;'>"
                    f"Showing page <b>{blotter_page}</b> of <b>{total_pages}</b> · {len(page_results)} visible rows"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            _render_metrics(results, stats, scan_time)

            with st.expander("Advanced Analysis", expanded=False):
                _render_breakout_readiness_panel(
                    filtered_results if filtered_results is not None and len(filtered_results) > 0 else results,
                    load_ticker_history,
                    load_nifty_history,
                    nested=True,
                )
                _render_multi_timeframe_panel(
                    filtered_results if filtered_results is not None and len(filtered_results) > 0 else results,
                    load_ticker_history,
                    {},
                    settings,
                    nested=True,
                )
    else:
        st.markdown(
            '<div class="glass-card" style="text-align:center;padding:48px 24px;">'
            '<div style="font-size:3rem;margin-bottom:12px;">⚡</div>'
            '<div style="font-size:1.1rem;font-weight:600;color:#00e5ff;margin-bottom:8px;">Scanner is standing by</div>'
            '<div style="color:#8899bb;font-size:0.9rem;">Choose Fresh Scan or Use Cache in the sidebar, then click the action button to start.</div>'
            '<div style="display:inline-flex;align-items:center;gap:6px;margin-top:12px;padding:4px 10px;border-radius:999px;border:1px solid rgba(0,229,255,0.22);background:rgba(0,229,255,0.08);color:#00e5ff;font-size:0.78rem;font-weight:600;">'
            '<span>↳</span><span>Click any row in Signal Blotter to open the detail page</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
