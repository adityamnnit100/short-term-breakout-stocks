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

    /* Trade Setup Workspace Styling */
    .terminal-panel {
        background: rgba(10, 20, 35, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 20px;
        height: 100%;
    }
    .terminal-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 20px;
    }
    .terminal-title {
        font-size: 1.2rem;
        font-weight: 700;
        color: #ffffff;
    }
    .terminal-subtitle {
        font-size: 0.8rem;
        color: #8899bb;
    }
    .terminal-badge {
        background: rgba(0, 229, 255, 0.1);
        color: #00e5ff;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.7rem;
        font-weight: bold;
        letter-spacing: 0.5px;
    }

    /* Signal Pills */
    .signal-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 50px;
        font-size: 0.75rem;
        margin-right: 8px;
        margin-bottom: 8px;
        font-weight: 600;
    }
    .sp-yes { background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); }
    .sp-no { background: rgba(255, 82, 82, 0.1); color: #ff5252; border: 1px solid rgba(255, 82, 82, 0.2); }

    /* Level Grid */
    .level-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 15px;
        margin-top: 20px;
    }
    .level-box {
        background: rgba(255, 255, 255, 0.03);
        padding: 12px;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .level-label { font-size: 0.7rem; color: #8899bb; margin-bottom: 4px; }
    .level-value { font-size: 1.1rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
    .level-entry { color: #00e5ff; }
    .level-sl { color: #ff5252; }
    .level-tp1 { color: #ffca28; }
    .level-tp2 { color: #00e676; }

    /* Trade Card */
    .trade-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 15px;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .trade-ticker { font-size: 1.8rem; font-weight: 800; color: #ffffff; }
    .trade-subtitle { font-size: 0.9rem; color: #8899bb; margin-bottom: 15px; }

    .strength-bar-wrap { height: 6px; background: rgba(255,255,255,0.05); border-radius: 10px; overflow: hidden; }
    .strength-bar { height: 100%; border-radius: 10px; transition: width 0.5s ease; }

    /* Metric Row and Scanner Status Styling */
    .metric-row {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 20px;
    }
    .metric-card {
        flex: 1;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 12px;
        border-radius: 12px;
    }
    .status-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin-top: 10px;
    }
    .status-label { font-size: 0.7rem; color: #8899bb; }
    .status-value { font-size: 0.9rem; font-weight: bold; color: #ffffff; }

    /* Mobile Responsiveness Overrides */
    @media (max-width: 768px) {
        .level-grid {
            grid-template-columns: 1fr;
        }
        .metric-row {
            flex-direction: column;
        }
        .status-grid {
            grid-template-columns: repeat(2, 1fr);
        }
        .trade-ticker {
            font-size: 1.4rem;
        }
        .terminal-panel {
            padding: 15px;
        }
        .terminal-head {
            flex-direction: column;
            gap: 10px;
        }
    }
</style>
""", unsafe_allow_html=True)

sidebar_settings, chart_options = render_sidebar(load_ticker_history, run_backtest_cached)

# Module Status Indicator
with st.sidebar:
    st.divider()
    st.caption("🧩 SYSTEM MODULES")
    if news.HAS_TEXTBLOB:
        st.success("Sentiment Engine: ACTIVE", icon="🧠")
    else:
        st.error("Sentiment Engine: MISSING", icon="🛑")
        st.caption("To enable, run: `pip install textblob`")

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
