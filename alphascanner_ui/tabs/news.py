"""News tab UI."""

import streamlit as st


def render_tab() -> None:
    st.markdown('<div class="glass-card"><div class="panel-title">Market News & Insights</div></div>', unsafe_allow_html=True)
    st.info(
        "📰 Connect an Alpha Vantage API key to enable live news sentiment. Set ALPHA_VANTAGE_API_KEY environment variable.",
        icon="ℹ️",
    )
    news_ticker = st.text_input("Filter news by ticker (optional)", placeholder="e.g. RELIANCE.NS")
    if st.button("🔄 Refresh News"):
        st.session_state["_news_ticker"] = news_ticker
    st.caption("News feed requires a valid Alpha Vantage API key.")
