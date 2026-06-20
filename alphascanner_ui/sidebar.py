"""Sidebar controls and app configuration models."""

from dataclasses import dataclass
from typing import Tuple

import streamlit as st


@dataclass(frozen=True)
class SidebarSettings:
    universe: str
    vol_thresh: float
    rsi_range: Tuple[int, int]
    dist_thresh: float
    min_mkt_cap: int
    max_mkt_cap: int
    scanner_type: str
    timeframe: str
    use_cache: bool
    include_news: bool
    only_ready_setups: bool


@dataclass(frozen=True)
class ChartOptions:
    show_sma: bool
    show_ema: bool
    show_bb: bool
    show_rsi: bool
    show_macd: bool
    show_vwap: bool


def render_sidebar(load_ticker_history, run_backtest_cached) -> Tuple[SidebarSettings, ChartOptions]:
    # Ensure critical session defaults exist to avoid KeyError and keep UI consistent
    st.session_state.setdefault("only_ready_setups", False)
    st.session_state.setdefault("chart_show_sma", True)
    st.session_state.setdefault("chart_show_ema", True)
    st.session_state.setdefault("chart_show_bb", True)
    st.session_state.setdefault("chart_show_rsi", True)
    st.session_state.setdefault("chart_show_macd", True)
    st.session_state.setdefault("chart_show_vwap", False)
    st.session_state.setdefault("include_news_sentiment", False)

    with st.sidebar:
        # Interactive Brand Section
        if st.button("⚡ ALPHASCANNER PRO\nTerminal Workspace", key="sidebar_brand_btn", use_container_width=True, help="Click to refresh terminal state"):
            st.session_state.run_scan = False
            st.rerun()

        st.divider()

        with st.expander("🎯 Filter Parameters", expanded=True):
            universe = st.selectbox(
                "Universe",
                ["Nifty 500", "Total Market (Cap Focused)"],
                index=0,
                help="Use Nifty 500 for the core scanner, or Total Market when you want market-cap screening.",
            )
            # persist short-term_sidebar selections
            st.session_state["sidebar_universe"] = universe
            scanner_type = st.selectbox(
                "Scanner Type",
                ["Breakout", "Pre-Breakout", "FII Accumulation", "Long-Term"],
                index=0,
                help="Breakout: active breakouts. Pre-Breakout: consolidating near highs. FII Accumulation: quarterly institutional holding build-up. Long-Term: large-cap stocks for longer holds.",
            )
            st.session_state["sidebar_scanner_type"] = scanner_type
            if scanner_type == "FII Accumulation":
                st.caption("Quarterly ownership scanner based on FII holding increasing quarter-on-quarter.")
                universe = "Screener.in FII QoQ"
                vol_thresh = st.slider("Min FII Increase (%)", 0.1, 10.0, 1.0, 0.1)
                rsi_range = (0, 100)
                dist_thresh = 0.0
                timeframe = "quarterly"
                min_mkt_cap = st.number_input(
                    "Min Market Cap (Cr)",
                    min_value=100,
                    max_value=500000,
                    value=1000,
                    step=100,
                    help="Default ₹1,000 Cr as requested.",
                )
                max_mkt_cap = 0
            elif scanner_type == "Long-Term":
                st.caption("Long-term investment scanner for large-cap stocks with market cap >1000 Cr.")
                universe = "Nifty 500"
                vol_thresh = st.slider("Min Volume Ratio (×avg)", 0.1, 5.0, 0.5, 0.1, help="Lower = more results, Higher = quality filter")
                rsi_range = (30, 70)
                dist_thresh = 0.0
                timeframe = "1d"
                min_mkt_cap = 1000
                max_mkt_cap = 0
            else:
                vol_thresh = st.slider("Min Volume Ratio (×avg)", 0.1, 5.0, 1.0 if scanner_type == "Breakout" else 0.6, 0.1, help="Lower = more results, Higher = quality filter")
                timeframe_choice = st.selectbox(
                    "Timeframe",
                    ["Daily", "60m", "30m", "15m", "5m"],
                    index=0,
                    help="Choose the analysis timeframe for the scan. Intraday intervals are useful for short-term setups.",
                )
                interval_map = {"Daily": "1d", "60m": "60m", "30m": "30m", "15m": "15m", "5m": "5m"}
                timeframe = interval_map.get(timeframe_choice, "1d")
                st.session_state["sidebar_timeframe"] = timeframe

                if scanner_type == "Breakout":
                    rsi_range = st.slider("RSI Range", 0, 100, (50, 85), help="Momentum zone for breakouts. Default 50-85 is broader for more scan results.")
                    dist_thresh = st.slider("Breakout Distance (%)", 0.5, 5.0, 1.5, 0.1)
                else: # Pre-Breakout
                    rsi_range = st.slider("RSI Range", 0, 100, (35, 70), help="RSI range for accumulation phase. Default 35-70 for more setups.")
                    dist_thresh = st.slider("Proximity to High (%)", 0.5, 10.0, 5.0, 0.5, help="How close to 20D/52W high for pre-breakout.")
                min_mkt_cap, max_mkt_cap = 0, 1000000
                if universe == "Total Market (Cap Focused)":
                    mkt_cap_range = st.slider(
                        "Market Cap Range (Cr)",
                        0, 100000, (500, 20000), 100,
                        help="Focus on Small Caps (<5k) or Mid Caps (5k-20k).",
                    )
                    min_mkt_cap, max_mkt_cap = mkt_cap_range
                # persist numeric filters
                st.session_state["sidebar_min_mkt_cap"] = min_mkt_cap
                st.session_state["sidebar_max_mkt_cap"] = max_mkt_cap
                st.session_state["sidebar_vol_thresh"] = vol_thresh
                st.session_state["sidebar_rsi_range"] = rsi_range
                st.session_state["sidebar_dist_thresh"] = dist_thresh

        st.divider()

        # Load chart options and news sentiment from session state
        # (configured in settings tab)
        chart_options = ChartOptions(
            show_sma=st.session_state.get("chart_show_sma", True),
            show_ema=st.session_state.get("chart_show_ema", True),
            show_bb=st.session_state.get("chart_show_bb", True),
            show_rsi=st.session_state.get("chart_show_rsi", True),
            show_macd=st.session_state.get("chart_show_macd", True),
            show_vwap=st.session_state.get("chart_show_vwap", False),
        )
        include_news = st.session_state.get("include_news_sentiment", False)

        cache_choice = st.radio("Data Source", ["🔄 Fresh Scan", "⏱ Use Cache (12h)"], index=0)
        use_cache = cache_choice == "⏱ Use Cache (12h)"
        st.session_state["sidebar_use_cache"] = use_cache
        action_label = "Load Cached Scan" if use_cache else "Run Fresh Scan"
        action_help = "Load the latest cached scan result" if use_cache else "Run a fresh market scan"

        st.divider()
        only_ready_setups = st.checkbox(
            "Only Ready Setups",
            value=st.session_state.get("only_ready_setups", False),
            help="Show only setups that meet the short-term execution readiness criteria.",
        )
        st.session_state["only_ready_setups"] = only_ready_setups

        st.divider()
        st.caption(f"Action: {action_label}")
        if st.button(action_label, use_container_width=True, help=action_help, key="primary_scan_action"):
            st.session_state.run_scan = True
            if not use_cache:
                st.session_state.results = None

    settings = SidebarSettings(
        universe=universe,
        vol_thresh=vol_thresh,
        rsi_range=rsi_range,
        dist_thresh=dist_thresh,
        min_mkt_cap=min_mkt_cap,
        max_mkt_cap=max_mkt_cap,
        scanner_type=scanner_type,
        timeframe=timeframe,
        use_cache=use_cache,
        include_news=include_news,
        only_ready_setups=only_ready_setups,
    )
    # Persist last-used settings for other UI components
    st.session_state["sidebar_last_settings"] = {
        "universe": settings.universe,
        "scanner_type": settings.scanner_type,
        "timeframe": settings.timeframe,
        "use_cache": settings.use_cache,
    }
    return settings, chart_options
