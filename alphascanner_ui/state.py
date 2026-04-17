"""Session state initialization."""

import copy

import streamlit as st


DEFAULT_SESSION_STATE = {
    "authenticated": False,
    "auth_user": None,
    "auth_is_admin": False,
    "workspace_loaded_for": None,
    "results": None,
    "stats": None,
    "last_scan_time": None,
    "last_toast_scan_time": None,
    "scan_source": None,
    "run_scan": False,
    "scan_running": False,
    "bt_results": None,
    "watchlist": [],
    "portfolios": [],
    "portfolio_positions": [],
    "trade_journal": [],
    "ticker_cache_refreshed_at": None,
    "backtest_cache_refreshed_at": None,
}


def init_session_state() -> None:
    """Populate expected Streamlit session-state keys on first load."""
    for key, value in DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)
