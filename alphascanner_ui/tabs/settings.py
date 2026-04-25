"""Settings tab UI."""

import datetime
from pathlib import Path

import streamlit as st

from breakout import clear_metadata_cache
from alphascanner_ui.auth import render_user_management


@st.dialog("Reset Confirmation")
def confirm_reset_dialog(action_fn, label):
    st.write(f"Are you sure you want to reset the **{label}**?")
    st.warning("This operation is immediate and cannot be reversed. Initial loading times for subsequent scans will increase.")
    if st.button("Confirm and Clear", type="primary", use_container_width=True):
        action_fn()
        st.rerun()


def render_tab(load_ticker_history, run_backtest_cached) -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">System Settings</div></div>', unsafe_allow_html=True)

    render_user_management()

    st.markdown("### View & Density")
    view_col_1, view_col_2 = st.columns(2)
    with view_col_1:
        st.session_state.compact_mode = st.toggle(
            "Compact Mode",
            value=bool(st.session_state.get("compact_mode", False)),
            help="Reduces spacing and card padding for a denser trading desk layout.",
        )
        st.session_state.focus_mode = st.toggle(
            "Scanner Focus Mode",
            value=bool(st.session_state.get("focus_mode", False)),
            help="Keeps the scanner focused on blotter, setup workspace, chart, and core risk context.",
        )
    with view_col_2:
        st.session_state.show_top_picks = st.toggle(
            "Show Top Picks",
            value=bool(st.session_state.get("show_top_picks", True)),
            disabled=bool(st.session_state.get("focus_mode", False)),
        )
        st.session_state.show_macro_context = st.toggle(
            "Show Macro Context",
            value=bool(st.session_state.get("show_macro_context", True)),
            disabled=bool(st.session_state.get("focus_mode", False)),
        )
        st.session_state.show_watchlist_quick_add = st.toggle(
            "Show Watchlist Quick Add",
            value=bool(st.session_state.get("show_watchlist_quick_add", True)),
            disabled=bool(st.session_state.get("focus_mode", False)),
        )
    st.caption("Focus Mode temporarily hides secondary scanner panels. Your data and watchlists are unchanged.")

    st.divider()
    st.markdown("### 🧹 Cache Management")
    cache_col_1, cache_col_2, cache_col_3 = st.columns(3)
    with cache_col_1:
        if st.button("🗑 Reset Ticker Cache", use_container_width=True):
            confirm_reset_dialog(load_ticker_history.clear, "Ticker History Cache")
    with cache_col_2:
        if st.button("🗑 Reset Backtest Cache", use_container_width=True):
            confirm_reset_dialog(run_backtest_cached.clear, "Backtest Results Cache")
    with cache_col_3:
        if st.button("🗑 Reset Metadata Cache", use_container_width=True):
            confirm_reset_dialog(clear_metadata_cache, "Fundamental Metadata Cache")

    st.divider()
    st.markdown("### 📝 Application Logs")
    if st.checkbox("Show latest logs"):
        log_path = Path(f"data/logs/alphascanner_{datetime.date.today()}.log")
        if log_path.exists():
            st.code(log_path.read_text().splitlines()[-20:], language="text")
