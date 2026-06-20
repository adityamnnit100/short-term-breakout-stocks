"""Theme, page chrome, and shared markup."""

from typing import Optional

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st


GLOBAL_STYLES = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
    --navy-900: #020617;
    --navy-800: #0f172a;
    --navy-700: #1e293b;
    --navy-600: #162b55;
    --navy-500: #1e3a6e;
    --slate:    #7b8aa5;
    --cyan:     #22d3ee;
    --cyan-dim: #0891b2;
    --green:    #10b981;
    --red:      #f43f5e;
    --amber:    #f59e0b;
    --purple:   #8b5cf6;
    --text:     #e8f0fe;
    --muted:    #cbd5e1;
    --border:   rgba(0,229,255,0.12);
    --card-bg:  rgba(14, 32, 64, 0.85);
    --glass:    rgba(255,255,255,0.04);
}

html, body, .stApp {
    font-family: 'Plus Jakarta Sans', sans-serif;
    background:
        radial-gradient(circle at top left, rgba(0,229,255,0.07), transparent 30%),
        radial-gradient(circle at top right, rgba(245,158,11,0.05), transparent 22%),
        linear-gradient(180deg, #020617 0%, #0f172a 100%);
    color: var(--text);
}
.block-container { padding: 0.5rem 1rem 2rem; max-width: 100%; }
[data-testid="stSidebar"] {
    min-width: 260px !important;
    max-width: 260px !important;
}
.stSidebar > div:first-child {
    background:
        linear-gradient(180deg, #020617 0%, #0f172a 100%);
    border-right: 1px solid rgba(0,229,255,0.1);
}
footer { visibility: hidden; }

.stApp,
.stApp p,
.stApp li,
.stApp label,
.stApp .stMarkdown,
.stApp .stCaption,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stExpander"] summary,
.stApp [data-testid="stExpander"] summary p,
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stAlertContainer"],
.stApp [data-testid="stAlertContainer"] * {
    color: var(--text);
}

.stApp .stCaption,
.stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stExpander"] summary p {
    color: var(--muted) !important;
}

.metric-row { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 20px; }
.metric-card, .glass-card, .section-container {
    background: linear-gradient(180deg, rgba(13,26,46,0.92) 0%, rgba(11,23,40,0.95) 100%);
    border: 1px solid rgba(0,229,255,0.1);
    border-radius: 14px; padding: 14px 16px;
    backdrop-filter: blur(14px);
    transition: all 0.2s ease;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 8px 24px rgba(0,0,0,0.3);
}
.glass-card.glow {
    border: 1px solid rgba(0, 229, 255, 0.4);
    box-shadow: 0 0 15px rgba(0, 229, 255, 0.1);
}
.metric-card:hover, .glass-card:hover { border-color: rgba(0,229,255,0.22); transform: translateY(-2px); }
.metric-label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
.metric-value { font-size: 1.55rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text); }
.metric-delta { font-size: 0.75rem; margin-top: 3px; }
.metric-delta.up   { color: var(--green); }
.metric-delta.down { color: var(--red); }
.metric-delta.neutral { color: var(--muted); }

.panel-title { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1.2px; color: var(--cyan); margin-bottom: 16px; font-weight: 700; border-left: 3px solid var(--cyan); padding-left: 10px; }

/* News / link visibility improvements */
.glass-card a { color: var(--cyan) !important; text-decoration: none !important; word-break: break-word; display: block; }
.glass-card a:hover { color: #dffbff !important; text-decoration: underline !important; }
.glass-card .news-publisher { color: var(--muted) !important; font-size: 0.82rem; margin-bottom: 4px; }
.glass-card .news-title { color: var(--cyan) !important; font-weight: 700; font-size: 1.05rem; line-height: 1.35; }

.trade-card {
    background: linear-gradient(135deg, rgba(14,32,64,0.95) 0%, rgba(10,25,50,0.95) 100%);
    border: 1px solid rgba(0,229,255,0.25); border-radius: 16px; padding: 24px;
    margin: 20px 0; box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.trade-card > div:first-child { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
.level-grid { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.trade-ticker { font-size: 1.4rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--cyan); }
.trade-subtitle { color: var(--muted); font-size: 0.82rem; margin-top: 2px; }
.level-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 20px; }
.level-box { background: var(--glass); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; }
.level-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.8px; color: var(--muted); margin-bottom: 4px; }
.level-value { font-size: 1.1rem; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
.level-entry  { color: var(--cyan); }
.level-sl     { color: var(--red); }
.level-tp1    { color: var(--amber); }
.level-tp2    { color: var(--green); }

.signal-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px; font-size: 0.75rem;
    font-family: 'JetBrains Mono', monospace; margin: 2px;
}
.sp-yes { background: rgba(16, 185, 129, 0.12); border: 1px solid var(--green); color: var(--green); }
.sp-no  { background: rgba(244, 63, 94, 0.10); border: 1px solid var(--red);  color: var(--red); }
.sp-info{ background: rgba(34, 211, 238, 0.10); border: 1px solid var(--cyan);  color: var(--cyan); }

.strength-bar-wrap { height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; margin-top: 4px; }
.strength-bar      { height: 6px; border-radius: 3px; transition: width 0.6s ease; }

/* Interactive Sidebar Brand Styling */
button[key="sidebar_brand_btn"] {
    background: linear-gradient(180deg, rgba(13,26,46,0.92) 0%, rgba(11,23,40,0.95) 100%) !important;
    border: 1px solid rgba(0,229,255,0.2) !important;
    padding: 20px !important;
    height: auto !important;
    white-space: pre-wrap !important;
    text-align: left !important;
    line-height: 1.4 !important;
    font-family: 'JetBrains Mono', monospace !important;
}
button[key="sidebar_brand_btn"]:hover {
    border-color: var(--cyan) !important;
    box-shadow: 0 0 20px rgba(0, 229, 255, 0.15) !important;
    transform: translateY(-2px);
}

.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(0,229,255,0.08);
    border-radius: 12px;
    padding: 6px;
    gap: 6px;
    margin-bottom: 14px;
}
.stTabs [data-baseweb="tab"], .stTabs [data-baseweb="tab"]:focus {
    background: transparent !important;
    color: var(--muted);
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.82rem;
    font-weight: 600;
}
.stTabs [data-baseweb="tab"] * {
    color: inherit !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(0,229,255,0.13), rgba(0,184,204,0.08)) !important;
    color: #dffbff !important;
    border: 1px solid rgba(0,229,255,0.14) !important;
}

.sidebar-section { margin-bottom: 20px; }
.sidebar-label   { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.8px; color: var(--muted); margin-bottom: 8px; }

div[data-testid="stMetricValue"]  { font-family: 'JetBrains Mono', monospace; color: var(--text) !important; }
div[data-testid="stMetricLabel"]  { color: var(--muted) !important; font-size: 0.75rem !important; }
div[data-testid="stMetricDelta"]  { font-family: 'JetBrains Mono', monospace; }
.stDataFrame thead th             { background: var(--navy-700) !important; color: var(--cyan-dim) !important; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }
.stDataFrame tbody td             { font-family: 'JetBrains Mono', monospace; font-size: 0.88rem; }
.stDataFrame, [data-testid="stDataFrame"] {
    border: 1px solid rgba(0,229,255,0.08);
    border-radius: 14px;
    overflow: hidden;
}
.stButton > button {
    background: linear-gradient(135deg, rgba(17,47,92,0.95), rgba(25,66,120,0.95)) !important;
    color: #e8f7ff !important; border: 1px solid rgba(0,229,255,0.12) !important;
    -webkit-text-fill-color: #e8f7ff !important;
    border-radius: 10px !important; font-weight: 600 !important;
    transition: all 0.2s !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04) !important;
}
.stButton > button * {
    color: #e8f7ff !important;
    -webkit-text-fill-color: #e8f7ff !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #1a3f7a, #2550a0) !important;
    border-color: var(--cyan) !important; transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(0,229,255,0.2) !important;
}
[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] .stButton > button,
.stSidebar .stButton > button {
    background: linear-gradient(135deg, #06364a, #0b6b86) !important;
    background-color: #0b6b86 !important;
    color: #f4fcff !important;
    -webkit-text-fill-color: #f4fcff !important;
    border: 1px solid rgba(0,229,255,0.42) !important;
}
[data-testid="stSidebar"] .stButton > button *,
section[data-testid="stSidebar"] .stButton > button *,
.stSidebar .stButton > button * {
    color: #f4fcff !important;
    -webkit-text-fill-color: #f4fcff !important;
    opacity: 1 !important;
}
[data-testid="stSidebar"] .stButton > button:hover,
section[data-testid="stSidebar"] .stButton > button:hover,
.stSidebar .stButton > button:hover {
    background: linear-gradient(135deg, #0a4963, #1183a1) !important;
    background-color: #1183a1 !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stSidebar"] .stButton > button:disabled,
section[data-testid="stSidebar"] .stButton > button:disabled,
.stSidebar .stButton > button:disabled,
[data-testid="stSidebar"] .stButton > button[disabled],
section[data-testid="stSidebar"] .stButton > button[disabled],
.stSidebar .stButton > button[disabled] {
    background: linear-gradient(135deg, #0b3b50, #0f5870) !important;
    background-color: #0f5870 !important;
    color: #eefcff !important;
    -webkit-text-fill-color: #eefcff !important;
    opacity: 1 !important;
}
[data-testid="stSidebar"] .stButton > button:disabled *,
section[data-testid="stSidebar"] .stButton > button:disabled *,
.stSidebar .stButton > button:disabled *,
[data-testid="stSidebar"] .stButton > button[disabled] *,
section[data-testid="stSidebar"] .stButton > button[disabled] *,
.stSidebar .stButton > button[disabled] * {
    color: #eefcff !important;
    -webkit-text-fill-color: #eefcff !important;
    opacity: 1 !important;
}
.stExpander {
    border: 1px solid rgba(0,229,255,0.08) !important;
    border-radius: 12px !important;
    background: rgba(255,255,255,0.015) !important;
}
.stRadio > label, .stSlider label, .stNumberInput label, .stCheckbox label, .stTextInput label, .stSelectbox label {
    font-size: 0.78rem !important;
    letter-spacing: 0.03rem;
}
.stSlider > div > div > div > div { background: var(--cyan) !important; }
.stSelectbox > div > div,
.stMultiSelect > div > div,
.stDateInput > div > div,
.stNumberInput > div > div,
.stTextInput > div > div,
.stTextArea > div > div {
    background: var(--card-bg) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
}
.stTextInput > div > div > input,
.stTextArea textarea,
.stDateInput input,
.stNumberInput input {
    background: transparent !important;
    color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important;
}
[data-baseweb="select"] *,
[data-baseweb="base-input"] *,
[data-baseweb="input"] * {
    color: var(--text) !important;
}
[data-baseweb="tag"] {
    background: rgba(0,229,255,0.08) !important;
    border: 1px solid rgba(0,229,255,0.14) !important;
}
[data-baseweb="tag"] * {
    color: var(--text) !important;
}
.stCheckbox p,
.stRadio p,
.stSlider p,
.stSelectbox p,
.stNumberInput p,
.stDateInput p,
.stTextInput p,
.stTextArea p {
    color: var(--muted) !important;
}
hr, .stDivider                    { border-color: var(--border) !important; }

.status-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
}
.status-cell {
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.06);
    background: rgba(255,255,255,0.025);
}
.status-label {
    color: var(--slate);
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0.12rem;
    margin-bottom: 6px;
}
.status-value {
    color: var(--text);
    font-size: 1rem;
    font-family: 'JetBrains Mono', monospace;
}

.market-tape {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 10px;
    margin: 6px 0 18px;
}
.tape-card {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.06);
    background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.015));
}
.tape-card.up { border-color: rgba(0,230,118,0.2); box-shadow: inset 0 0 0 1px rgba(0,230,118,0.05); }
.tape-card.down { border-color: rgba(255,82,82,0.2); box-shadow: inset 0 0 0 1px rgba(255,82,82,0.05); }
.tape-label {
    font-size: 0.68rem;
    color: var(--slate);
    text-transform: uppercase;
    letter-spacing: 0.08rem;
    margin-bottom: 6px;
}
.tape-price {
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.98rem;
}
.tape-change {
    margin-top: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
}
.tape-change.up { color: var(--green); }
.tape-change.down { color: var(--red); }

.top-picks-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
}
.top-pick-card {
    background: linear-gradient(160deg, rgba(8,31,49,0.95), rgba(11,23,40,0.95));
    border: 1px solid rgba(0,229,255,0.14);
    border-radius: 14px;
    padding: 14px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
}
.top-pick-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
}
.top-pick-symbol {
    font-size: 1rem;
    font-weight: 700;
    color: #dffbff;
    font-family: 'JetBrains Mono', monospace;
}
.top-pick-price {
    font-size: 1rem;
    font-family: 'JetBrains Mono', monospace;
    color: var(--cyan);
}
.top-pick-meta {
    font-size: 0.76rem;
    color: var(--muted);
    margin-bottom: 10px;
    min-height: 2.2em;
}
.top-pick-tags {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.mini-tag {
    font-size: 0.68rem;
    font-family: 'JetBrains Mono', monospace;
    color: var(--cyan-dim);
    background: rgba(0,229,255,0.08);
    border: 1px solid rgba(0,229,255,0.14);
    border-radius: 999px;
    padding: 4px 8px;
}

.terminal-panel {
    background: linear-gradient(180deg, rgba(10,20,35,0.96) 0%, rgba(8,17,31,0.98) 100%);
    border: 1px solid rgba(0,229,255,0.1);
    border-radius: 16px;
    padding: 14px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 16px 40px rgba(0,0,0,0.22);
}
.terminal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
}
.terminal-title {
    color: var(--text);
    font-size: 0.85rem;
    font-weight: 700;
    letter-spacing: 0.1rem;
    text-transform: uppercase;
}
.terminal-subtitle {
    color: var(--slate);
    font-size: 0.74rem;
}
.terminal-badge {
    color: var(--cyan);
    border: 1px solid rgba(0,229,255,0.14);
    background: rgba(0,229,255,0.08);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 0.7rem;
    font-family: 'JetBrains Mono', monospace;
}

@media (prefers-color-scheme: light) {
    :root {
        --slate: #64748b;
        --text: #0f172a;
        --muted: #475569;
        --border: rgba(14, 116, 144, 0.16);
        --card-bg: rgba(255,255,255,0.88);
        --glass: rgba(15,23,42,0.03);
        --cyan: #0891b2;
        --cyan-dim: #0e7490;
        --navy-700: #e8f4ff;
        --green: #059669;
        --red: #dc2626;
        --amber: #d97706;
    }

    html, body, .stApp {
        background:
            radial-gradient(circle at top left, rgba(14,165,233,0.09), transparent 28%),
            radial-gradient(circle at top right, rgba(245,158,11,0.05), transparent 20%),
            linear-gradient(180deg, #f7fbff 0%, #eef6ff 46%, #f8fbff 100%);
        color: var(--text);
    }

    .stSidebar > div:first-child {
        background: linear-gradient(180deg, rgba(248,251,255,0.98) 0%, rgba(238,246,255,0.98) 100%);
        border-right: 1px solid rgba(14,116,144,0.14);
    }

    .hero-header {
        background: linear-gradient(125deg, rgba(255,255,255,0.95) 0%, rgba(239,248,255,0.96) 55%, rgba(245,250,255,0.98) 100%);
        border: 1px solid rgba(14,116,144,0.16);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.7), 0 18px 40px rgba(148,163,184,0.18);
    }

    .hero-header::after {
        background:
            linear-gradient(rgba(15,23,42,0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(15,23,42,0.03) 1px, transparent 1px);
    }

    .hero-header::before {
        background: radial-gradient(ellipse, rgba(14, 165, 233, 0.08) 0%, transparent 70%);
    }

    .hero-kicker {
        color: var(--slate);
    }
    .hero-title {
        background: linear-gradient(90deg, #0f172a, #0891b2 45%, #0e7490 100%);
    }

    .terminal-sidebar-brand,
    .metric-card,
    .glass-card,
    .section-container,
    .terminal-panel,
    .top-pick-card,
    .trade-card,
    .hero-stat,
    .tape-card,
    .status-cell,
    .level-box {
        background: linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(248,251,255,0.96) 100%) !important;
        border-color: rgba(14,116,144,0.14) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.75), 0 12px 28px rgba(148,163,184,0.16) !important;
    }

    .badge,
    .mini-tag,
    .terminal-badge {
        background: rgba(14,165,233,0.08) !important;
        border-color: rgba(14,165,233,0.18) !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.66);
        border-color: rgba(14,116,144,0.14);
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(14,165,233,0.14), rgba(56,189,248,0.12)) !important;
        color: #0f172a !important;
        border-color: rgba(14,165,233,0.22) !important;
    }

    .stDataFrame thead th {
        background: #e8f4ff !important;
        color: #0f172a !important;
    }

    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    .stDateInput > div > div,
    .stNumberInput > div > div,
    .stTextInput > div > div,
    .stTextArea > div > div {
        background: rgba(255,255,255,0.92) !important;
        border: 1px solid rgba(14,116,144,0.16) !important;
        color: #0f172a !important;
    }
}

@media (max-width: 1100px) {
    .hero-grid, .status-grid, .market-tape, .top-picks-grid, .hero-stats, .metric-row, .level-grid {
        grid-template-columns: 1fr 1fr;
    }
}
@media (max-width: 760px) {
    .hero-grid, .status-grid, .market-tape, .top-picks-grid, .hero-stats, .metric-row, .level-grid {
        grid-template-columns: 1fr;
    }
}
</style>
"""


def apply_global_styles() -> None:
    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)

def apply_plotly_theme() -> None:
    """Register and set the default Plotly theme for AlphaScanner PRO."""
    
    # Using transparent backgrounds to inherit the dashboard gradient
    COLOR_BG = "rgba(0,0,0,0)" 
    COLOR_GRID = "rgba(255, 255, 255, 0.05)"
    COLOR_TEXT = "#e8f0fe"
    COLOR_ACCENT = "#00ffaa"
    COLOR_MUTE = "#7b8aa5"

    template = go.layout.Template()
    template.layout = go.Layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        font=dict(color=COLOR_TEXT, family="'Plus Jakarta Sans', sans-serif"),
        xaxis=dict(
            gridcolor=COLOR_GRID,
            zerolinecolor=COLOR_GRID,
            tickfont=dict(color=COLOR_MUTE, size=11),
            linecolor=COLOR_GRID,
            showgrid=True,
        ),
        yaxis=dict(
            gridcolor=COLOR_GRID,
            zerolinecolor=COLOR_GRID,
            tickfont=dict(color=COLOR_MUTE, size=11),
            linecolor=COLOR_GRID,
            showgrid=True,
        ),
        legend=dict(
            bgcolor=COLOR_BG,
            font=dict(color=COLOR_TEXT, size=12),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        hoverlabel=dict(
            bgcolor="#1e1e26",
            bordercolor=COLOR_ACCENT,
            font=dict(color="#ffffff", size=13),
        ),
        colorway=[COLOR_ACCENT, "#22d3ee", "#f43f5e", "#f59e0b", "#8b5cf6"],
        margin=dict(t=50, b=40, l=50, r=20),
    )
    
    pio.templates["alphascanner_pro"] = template
    pio.templates.default = "alphascanner_pro"

def render_footer(last_scan_time: Optional[str]) -> None:
    st.markdown(
        f"""
<div style="text-align:center;padding:24px 0 8px;color:#4a5568;font-size:0.72rem;font-family:'JetBrains Mono';">
    AlphaScanner PRO · Data: Yahoo Finance · Last scan: {last_scan_time or 'Never'}
</div>
""",
        unsafe_allow_html=True,
    )
