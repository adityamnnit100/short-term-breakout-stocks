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
    "watchlist": {"Default": []},
    "portfolios": [],
    "portfolio_positions": [],
    "trade_journal": [],
    "notes": [],
    "ticker_cache_refreshed_at": None,
    "backtest_cache_refreshed_at": None,
    "compact_mode": False,
    "focus_mode": False,
    "show_top_picks": True,
    "show_macro_context": True,
    "show_watchlist_quick_add": True,
    # Chart display settings
    "chart_show_sma": True,
    "chart_show_ema": True,
    "chart_show_bb": True,
    "chart_show_rsi": True,
    "chart_show_macd": True,
    "chart_show_vwap": False,
    # Advanced analysis features
    "include_news_sentiment": False,
    # Alerts configuration
    "alerts_enabled": False,
    "telegram_token": "",
    "telegram_chat_id": "",
    "whatsapp_webhook_url": "",
    "alert_breakout": True,
    "alert_pullback": True,
    "alert_pre_breakout_score": 7,  # Alert when setup score > this value
    "alert_entry_price_hit": True,
    "alert_target_hit": True,
    "alert_stop_hit": True,
    # Trailing stops configuration
    "trailing_stops_enabled": False,
    "trailing_stop_atr_multiplier": 1.5,
    "trailing_stop_max_profit_pct": 5.0,  # Lock in profits after this %
    "active_trailing_stops": {},  # Dict of {ticker: position_data}
    "trailing_stop_positions": [],  # List of active trailing stop positions
    # Intraday scanning
    "intraday_timeframes": ["Daily"],  # Can add 5m, 15m, 1h, 60m
}


def init_session_state() -> None:
    """Populate expected Streamlit session-state keys on first load."""
    for key, value in DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)
