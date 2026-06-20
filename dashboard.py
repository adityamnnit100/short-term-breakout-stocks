"""Streamlit entrypoint for AlphaScanner PRO."""

import streamlit as st
from alphascanner_ui.auth import render_logout_control, require_login
from alphascanner_ui.data import (
    configure_logging,
    fetch_indices_performance,
    fetch_fii_dii_data,
    load_nifty_history,
    load_ticker_history,
    run_backtest_cached,
)
from alphascanner_ui.database import init_db as init_user_db
from alphascanner_ui.sidebar import render_sidebar
from alphascanner_ui.state import init_session_state
from alphascanner_ui.tabs import backtest, journal, market, news, portfolio, risk, scanner, settings, watchlist, notes, alerts, performance
from alphascanner_ui.theme import apply_global_styles, apply_plotly_theme, render_footer


st.set_page_config(
    page_title="AlphaScanner PRO",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

logger = configure_logging()
init_session_state()
require_login()
init_user_db()

# Only run these after successful login to prevent UI flickering and state errors
try:
    # Defer heavy imports (yfinance/multitasking) until after core UI is ready.
    # This prevents import-time crashes in environments where those libs aren't compatible.
    from breakout import start_background_metadata_worker

    start_background_metadata_worker()
except Exception:
    logger.exception("Failed to start background metadata worker; continuing without it.")
apply_global_styles()
apply_plotly_theme()

# Custom CSS for modern metrics and Top Pick cards
st.markdown("""
<style>
    /* PURE TERMINAL LOOK: Remove header background but keep sidebar toggle visible */
    header[data-testid="stHeader"] {
        background: transparent !important;
        border: none !important;
    }
    .main .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 1rem !important;
    }

    /* Global Theme Overrides for Visibility */
    .stApp {
        background: radial-gradient(circle at top right, #f0f9ff, #e0f2fe) !important;
        color: #0f172a !important;
    }

    /* FORCE BLACK TEXT for all standard Streamlit containers */
    .stApp [data-testid="stMarkdownContainer"], .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp span, .stApp [data-testid="stWidgetLabel"] p {
        color: #000000 !important; /* Pure black for production-grade contrast */
        font-weight: 450;
    }

    /* Tab Navigation Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background-color: #ffffff !important;
        padding: 8px 16px !important;
        border-radius: 12px;
        border: 1px solid #bae6fd;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent !important;
        border-radius: 8px !important;
        padding: 8px 16px !important;
    }
    .stTabs [data-baseweb="tab"] p {
        color: #334155 !important; /* Darker slate for unselected tabs */
        font-weight: 600 !important;
        font-size: 1rem !important;
    }
    .stTabs [aria-selected="true"] p {
        color: #0284c7 !important;
        text-decoration: underline;
        font-weight: 700 !important;
    }

    /* Global Visibility & Backgrounds */
    .glass-card {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
    }

    /* Metric Box Styling */
    [data-testid="stMetric"] {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }
    [data-testid="stMetricValue"] {
        color: #020617 !important;
        font-weight: 800 !important;
    }
    [data-testid="stMetricLabel"] p {
        color: #0369a1 !important; /* Sky 700 labels for better visibility */
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stMetric"]:hover {
        background: #f0f9ff !important;
        border-color: #0284c7;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(2, 132, 199, 0.15);
    }

    /* Top Pick Card Layout */
    .top-pick-card {
        background: #ffffff;
        border-left: 4px solid #0284c7;
        padding: 16px;
        margin-bottom: 12px;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: transform 0.2s ease;
    }
    .top-pick-card:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 15px rgba(2, 132, 199, 0.15);
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
        color: #0369a1;
    }
    .top-pick-price {
        color: #0284c7;
        font-family: 'Courier New', monospace;
        font-weight: bold;
    }
    .top-pick-meta {
        font-size: 0.85rem;
        color: #94a3b8;
        margin-bottom: 10px;
    }
    .mini-tag {
        background: #e0f2fe;
        color: #0369a1;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        margin-right: 5px;
    }

    /* Trade Setup Workspace Styling */
    .terminal-panel {
        background: #ffffff !important;
        border: 1px solid #075985 !important; /* High contrast border */
        border-radius: 16px;
        padding: 20px;
        color: #0f172a;
        height: 100%;
        overflow-x: auto; /* Enable horizontal scroll for children */
    }
    .terminal-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 20px;
    }
    .terminal-title {
        font-size: 1.2rem;
        font-weight: 800;
        color: #0f172a;
    }
    .terminal-subtitle {
        font-size: 0.8rem;
        color: #475569;
    }
    .terminal-badge {
        background: #e0f2fe;
        color: #0369a1;
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
    .sp-yes { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .sp-no { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }

    /* Level Grid */
    .level-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 15px;
        margin-top: 20px;
    }
    .level-box {
        background: #f8fafc;
        padding: 12px;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
    }
    .level-label { font-size: 0.7rem; color: #64748b; margin-bottom: 4px; }
    .level-value { font-size: 1.1rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
    .level-entry { color: #0284c7; }
    .level-sl { color: #dc2626; }
    .level-tp1 { color: #b45309; }
    .level-tp2 { color: #15803d; }

    /* Trade Card */
    .trade-card {
        background: #ffffff;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 15px;
        border: 1px solid #e2e8f0;
    }
    .trade-ticker { font-size: 1.8rem; font-weight: 800; color: #0f172a; }
    .trade-subtitle { font-size: 0.9rem; color: #475569; margin-bottom: 15px; }

    /* Dynamic Strength Bar */
    .strength-bar-wrap { 
        height: 10px; 
        background: #f1f5f9; 
        border-radius: 10px; 
        overflow: hidden; 
        border: 1px solid #e2e8f0;
    }
    .strength-bar { height: 100%; border-radius: 10px; transition: width 0.5s ease; }

    /* Heat-Mapped Colors */
    .strength-high { background: linear-gradient(90deg, #0284c7, #0d9488); box-shadow: 0 0 10px rgba(13, 148, 136, 0.2); }
    .strength-mid { background: linear-gradient(90deg, #d97706, #059669); }
    .strength-low { background: linear-gradient(90deg, #dc2626, #ea580c); }
    .strength-trap { background: #ef4444; box-shadow: 0 0 15px rgba(239, 68, 68, 0.3); }

    /* Metric Row and Scanner Status Styling */
    .metric-row {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 20px;
    }
    .metric-card {
        flex: 1;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 12px;
        border-radius: 12px;
        color: #0f172a;
    }
    .status-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin-top: 10px;
    }
    .status-label { font-size: 0.75rem; color: #64748b; }
    .status-value { font-size: 0.9rem; font-weight: bold; color: #0f172a; }
    .metric-value { color: #0f172a; }
    
    /* Index/Metric Delta Coloring Fix */
    .metric-delta.neutral { color: #64748b; }
    .metric-delta.up, [data-testid="stMetricDelta"] > div[aria-label^="Increased"] { 
        color: #16a34a !important; 
    }
    .metric-delta.down, [data-testid="stMetricDelta"] > div[aria-label^="Decreased"] { 
        color: #dc2626 !important; 
    }

    .panel-title { color: #0f172a; font-weight: 700; }
    .trade-ticker { color: #0f172a; }

    /* Dataframe High-Contrast Borders & Container */
    [data-testid="stDataFrame"] {
        border: 2px solid #075985 !important; /* Bold high-contrast border for grids */
        border-radius: 8px !important;
        padding: 4px !important;
        background: #ffffff !important;
    }

    /* Visibility for Table elements if rendered as standard HTML */
    table {
        border-collapse: collapse !important;
        color: #0f172a !important;
    }
    th, td { border: 1px solid #cbd5e1 !important; }

    /* Sidebar Visibility Fixes */
    [data-testid="stSidebar"] {
        background-color: #e0f2fe !important;
    }
    [data-testid="stSidebar"] * {
        color: #0f172a !important;
    }

    /* Mobile Responsiveness Overrides */
    @media (max-width: 768px) {
        .glass-card { padding: 12px; }
        .level-grid {
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .metric-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .status-grid {
            grid-template-columns: repeat(2, 1fr);
        }
        .trade-ticker {
            font-size: 1.3rem;
        }
        .terminal-panel {
            padding: 15px;
            margin-bottom: 15px;
            overflow-x: auto; /* Allow the panel to scroll horizontally */
        }
        /* Force Charts to fill screen height on mobile */
        [data-testid="stPlotlyChart"] {
            height: 70vh !important;
            min-height: 400px;
        }
        /* Prevent column squashing in the Signal Blotter */
        [data-testid="stDataFrame"] {
            min-width: 1000px; /* Force minimum width to trigger horizontal scroll */
        }
        /* Enhanced Table Visibility */
        .stDataFrame div[data-testid="stHorizontalBlock"] {
            overflow-x: auto !important;
        }
        .terminal-head {
            flex-direction: column;
            gap: 10px;
        }
        /* Adjust components for small screens */
        [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 12px;
        }
    }
</style>
""", unsafe_allow_html=True)

sidebar_settings, chart_options = render_sidebar(load_ticker_history, run_backtest_cached)
render_logout_control()

# Apply 'Compact Mode' styles if enabled in Settings
if st.session_state.get('compact_mode', False):
    st.markdown("""
    <style>
        .glass-card, .terminal-panel, .trade-card { padding: 10px !important; border-radius: 8px !important; }
        .metric-card, [data-testid="stMetric"] { padding: 6px !important; }
        .panel-title, .terminal-title { font-size: 1rem !important; }
        .metric-value { font-size: 1rem !important; }
        .trade-ticker { font-size: 1.2rem !important; }
        .status-grid, .level-grid { gap: 4px !important; }
        .status-label, .level-label { font-size: 0.6rem !important; }
        .status-value, .level-value { font-size: 0.75rem !important; }
        .stTabs [data-baseweb="tab"] { padding: 4px 8px !important; font-size: 0.75rem !important; }
        .top-pick-card { padding: 8px !important; margin-bottom: 6px !important; }
        [data-testid="stMetricLabel"] p { font-size: 0.7rem !important; }
    </style>
    """, unsafe_allow_html=True)

tab_scanner, tab_backtest, tab_watchlist, tab_portfolio, tab_market, tab_news, tab_risk, tab_journal, tab_notes, tab_alerts, tab_settings, tab_performance = st.tabs(
    [
        "🎯 Scanner",
        "📈 Backtest",
        "📋 Watchlist",
        "💼 Portfolio",
        "🌍 Market",
        "📰 News",
        "⚠️ Risk Mgmt",
        "📝 Journal",
        "📒 Notes",
        "🔔 Alerts",
        "⚙️ Settings",
        "📊 Performance",
    ]
)

with tab_scanner:
    scanner.render_tab(sidebar_settings, chart_options, load_ticker_history, fetch_indices_performance) # scanner_type is now part of sidebar_settings
    # Smooth UI interaction: notify user when scan results are fresh
    if (
        st.session_state.get('last_scan_time')
        and not st.session_state.get('scan_running')
        and st.session_state.get('last_toast_scan_time') != st.session_state.last_scan_time
    ):
        st.toast(f"Latest opportunities loaded (Scan time: {st.session_state.last_scan_time})", icon="⚡")
        st.session_state.last_toast_scan_time = st.session_state.last_scan_time

with tab_backtest:
    backtest.render_tab(sidebar_settings, run_backtest_cached, load_nifty_history)

with tab_watchlist:
    watchlist.render_tab(load_ticker_history)

with tab_portfolio:
    portfolio.render_tab(load_ticker_history)

with tab_market:
    market.render_tab(fetch_indices_performance, fetch_fii_dii_data, load_nifty_history, logger)

with tab_news:
    news.render_tab()

with tab_risk:
    risk.render_tab()

with tab_journal:
    journal.render_tab()

with tab_notes:
    notes.render_tab()

with tab_alerts:
    alerts.render_tab(load_ticker_history)

with tab_settings:
    settings.render_tab(load_ticker_history, run_backtest_cached)

with tab_performance:
    performance.render()

render_footer(st.session_state.last_scan_time)
