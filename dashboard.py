"""Streamlit entrypoint for AlphaScanner PRO."""

import streamlit as st

from alphascanner_ui.data import (
    configure_logging,
    fetch_fii_dii_data,
    fetch_indices_performance,
    load_nifty_history,
    load_ticker_history,
    run_backtest_cached,
)
from alphascanner_ui.sidebar import render_sidebar
from alphascanner_ui.state import init_session_state
from alphascanner_ui.tabs import backtest, journal, market, news, risk, scanner, settings, watchlist
from alphascanner_ui.theme import apply_global_styles, apply_plotly_theme, render_footer, render_hero_header


st.set_page_config(
    page_title="AlphaScanner PRO",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

logger = configure_logging()
init_session_state()
apply_global_styles()
apply_plotly_theme()

# Custom CSS for modern metrics and Top Pick cards
st.markdown("""
<style>
    /* Metric Box Styling */
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        border-radius: 12px;
        transition: all 0.3s ease;
    }
    [data-testid="stMetric"]:hover {
        background: rgba(255, 255, 255, 0.08);
        border-color: #00ffaa;
        transform: translateY(-2px);
        box-shadow: 0 0 15px rgba(0, 255, 170, 0.15);
    }

    /* Top Pick Card Layout */
    .top-pick-card {
        background: linear-gradient(135deg, #1e1e26 0%, #121216 100%);
        border-left: 4px solid #00ffaa;
        padding: 16px;
        margin-bottom: 12px;
        border-radius: 8px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        transition: transform 0.2s ease;
    }
    .top-pick-card:hover {
        transform: scale(1.02);
        box-shadow: 0 8px 25px rgba(0, 255, 170, 0.2);
    }
    .top-pick-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    .top-pick-symbol {
        font-weight: 800;
        font-size: 1.1rem;
        color: #ffffff;
    }
    .top-pick-price {
        color: #00ffaa;
        font-family: 'Courier New', monospace;
        font-weight: bold;
    }
    .top-pick-meta {
        font-size: 0.85rem;
        color: #888;
        margin-bottom: 10px;
    }
    .mini-tag {
        background: rgba(0, 255, 170, 0.1);
        color: #00ffaa;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        margin-right: 5px;
    }
</style>
""", unsafe_allow_html=True)

sidebar_settings, chart_options = render_sidebar(load_ticker_history, run_backtest_cached)
render_hero_header()

tab_scanner, tab_backtest, tab_watchlist, tab_market, tab_news, tab_risk, tab_journal, tab_settings = st.tabs(
    [
        "🎯 Scanner",
        "📈 Backtest",
        "📋 Watchlist",
        "🌍 Market",
        "📰 News",
        "⚠️ Risk Mgmt",
        "📝 Journal",
        "⚙️ Settings",
    ]
)

with tab_scanner:
    scanner.render_tab(sidebar_settings, chart_options, load_ticker_history, fetch_indices_performance)
    # Smooth UI interaction: notify user when scan results are fresh
    if st.session_state.get('last_scan_time') and not st.session_state.get('scan_running'):
        st.toast(f"Latest opportunities loaded (Scan time: {st.session_state.last_scan_time})", icon="⚡")

with tab_backtest:
    backtest.render_tab(sidebar_settings, run_backtest_cached, load_nifty_history)

with tab_watchlist:
    watchlist.render_tab(load_ticker_history)

with tab_market:
    market.render_tab(fetch_indices_performance, fetch_fii_dii_data, load_nifty_history, logger)

with tab_news:
    news.render_tab()

with tab_risk:
    risk.render_tab()

with tab_journal:
    journal.render_tab()

with tab_settings:
    settings.render_tab(load_ticker_history, run_backtest_cached)

render_footer(st.session_state.last_scan_time)
