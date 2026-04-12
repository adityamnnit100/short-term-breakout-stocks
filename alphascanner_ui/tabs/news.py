"""News tab UI."""

import datetime
import streamlit as st
import yfinance as yf

try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False


def get_sentiment(text: str):
    """Perform basic sentiment analysis on article titles."""
    if not HAS_TEXTBLOB:
        return "NEUTRAL", "rgba(255, 255, 255, 0.05)", "#8899bb"
    analysis = TextBlob(text)
    score = analysis.sentiment.polarity
    if score > 0.1:
        return "BULLISH", "rgba(0, 230, 118, 0.15)", "#00e676"
    elif score < -0.1:
        return "BEARISH", "rgba(255, 82, 82, 0.15)", "#ff5252"
    return "NEUTRAL", "rgba(255, 255, 255, 0.05)", "#8899bb"


@st.cache_data(ttl=900, show_spinner=False)
def fetch_news_cached(query: str, news_count: int = 12):
    """Fetch news articles from Yahoo Finance with a 15-minute cache."""
    try:
        search = yf.Search(query, news_count=news_count)
        return search.news
    except Exception:
        return []


def render_tab() -> None:
    st.markdown('<div class="glass-card"><div class="panel-title">Market News & Insights</div></div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        news_ticker = st.text_input(
            "Filter news by ticker or keyword", 
            placeholder="e.g. RELIANCE.NS, Nifty 50, Tech Stocks",
            key="news_ticker_input"
        )
    with col2:
        st.write("") # Spacer for vertical alignment
        st.write("")
        refresh = st.button("🔄 Refresh News", use_container_width=True)
        if refresh:
            fetch_news_cached.clear()

    # Use "Indian Stock Market" as default if no query is provided
    query = news_ticker.strip() if news_ticker else "Indian Stock Market"
    
    with st.spinner(f"Fetching latest news for '{query}'..."):
        articles = fetch_news_cached(query, news_count=12)

    if articles is None:
        st.error("Could not fetch news at this time.")
        return

    if not articles:
        st.info("No recent news articles found for this query.")
        return

    # Sort articles by sentiment polarity (Bullish/highest score first)
    if HAS_TEXTBLOB:
        articles.sort(key=lambda x: TextBlob(x.get("title", "")).sentiment.polarity, reverse=True)

    for article in articles:
        title = article.get("title", "No Title")
        link = article.get("link", "#")
        publisher = article.get("publisher", "Unknown Source")
        pub_time = article.get("providerPublishTime", 0)
        date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M') if pub_time else "Recent"
        
        sentiment, bg, color = get_sentiment(title)

        st.markdown(f"""
            <div style="background: rgba(255, 255, 255, 0.05); padding: 1.2rem; border-radius: 12px; border-left: 4px solid #00e5ff; margin-bottom: 1rem; border-bottom: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 0.8rem; color: #8899bb; margin-bottom: 0.5rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                    <span>{publisher} • <span style="color: {color}; background: {bg}; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.7rem;">{sentiment}</span></span>
                    <span>{date_str}</span>
                </div>
                <a href="{link}" target="_blank" style="text-decoration: none; color: #00e5ff; font-weight: 600; font-size: 1.1rem; line-height: 1.4; display: block;">{title}</a>
            </div>
        """, unsafe_allow_html=True)

    if HAS_TEXTBLOB:
        st.caption("News data sourced from Yahoo Finance. Sentiment analysis powered by TextBlob.")
    else:
        st.caption("News data sourced from Yahoo Finance. Install 'textblob' to enable sentiment features.")
