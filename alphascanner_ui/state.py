"""Session state initialization."""

import streamlit as st


DEFAULT_SESSION_STATE = {
    "results": None,
    "stats": None,
    "last_scan_time": None,
    "scan_source": None,
    "run_scan": False,
    "bt_results": None,
    "watchlist": [],
    "portfolio_positions": [],
    "trade_journal": [],
    "ticker_cache_refreshed_at": None,
    "backtest_cache_refreshed_at": None,
}


def init_session_state() -> None:
    """Populate expected Streamlit session-state keys on first load."""
    for key, value in DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value
