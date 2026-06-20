"""News tab UI."""

import datetime
import html
import xml.etree.ElementTree as ET
import urllib.parse
import requests
import streamlit as st
from dateutil import parser as date_parser

try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False


def get_sentiment(text: str):
    """Perform basic sentiment analysis on article titles."""
    if not HAS_TEXTBLOB:
        return "NEUTRAL", "rgba(255, 255, 255, 0.05)", "#94a3b8"
    analysis = TextBlob(text)
    score = analysis.sentiment.polarity
    if score > 0.1:
        return "BULLISH", "rgba(0, 230, 118, 0.15)", "#00e676"
    elif score < -0.1:
        return "BEARISH", "rgba(255, 82, 82, 0.15)", "#ff5252"
    return "NEUTRAL", "rgba(255, 255, 255, 0.05)", "#94a3b8"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_news_cached(query: str, news_count: int = 15):
    """
    Fetch news articles with a focus on the Indian market.
    Prioritizes Google News RSS for better local relevance and recency.
    """
    news_results = []
    
    # 1. Try Google News RSS (High relevance for Indian business news)
    try:
        encoded_query = urllib.parse.quote(query)
        # Targeted parameters for India: hl=en-IN (language), gl=IN (region), ceid=IN:en
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for item in root.findall(".//item")[:news_count]:
                title = item.find("title").text if item.find("title") is not None else "No Title"
                link = item.find("link").text if item.find("link") is not None else "#"
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                source = item.find("source").text if item.find("source") is not None else "Unknown"
                
                try:
                    ts = int(date_parser.parse(pub_date).timestamp())
                except Exception:
                    ts = int(datetime.datetime.now().timestamp())
                
                # Clean title: Google News often appends " - Source" at the end
                display_title = title
                if source and title.endswith(source):
                    display_title = title[:-(len(source) + 3)].strip()
                
                news_results.append({
                    "title": display_title,
                    "link": link,
                    "publisher": source,
                    "providerPublishTime": ts
                })
    except Exception:
        pass 

    # 2. Fallback to Yahoo Finance Search if Google RSS fails or is empty
    if not news_results:
        try:
            import yfinance as yf

            search = yf.Search(query, news_count=news_count)
            news_results = getattr(search, "news", [])
        except Exception:
            pass
            
    return news_results


def render_tab() -> None:
    st.markdown('<div class="glass-card"><div class="panel-title" style="color: #00e5ff;">Market News & Insights</div></div>', unsafe_allow_html=True)
    
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

    # Use a more descriptive default for better Indian equity relevance
    query = news_ticker.strip() if news_ticker else "Nifty 50 Sensex Indian Equity Market News"
    
    with st.spinner(f"Fetching latest news for '{query}'..."):
        articles = fetch_news_cached(query, news_count=15)

    if articles is None:
        st.error("Could not fetch news at this time.")
        return

    if not articles:
        st.info("No recent news articles found for this query.")
        return

    # Sort articles by time (Most recent first) to ensure a real-time feed experience
    articles.sort(key=lambda x: x.get("providerPublishTime", 0), reverse=True)

    for article in articles:
        title = html.escape(str(article.get("title", "No Title")))
        link = html.escape(str(article.get("link", "#")), quote=True)
        publisher = html.escape(str(article.get("publisher", "Unknown Source")))
        pub_time = article.get("providerPublishTime", 0)
        date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M') if pub_time else "Recent"
        
        sentiment, bg, color = get_sentiment(title)

        st.markdown(f"""
            <div class="glass-card" style="padding: 1.2rem; border-left: 4px solid #00e5ff; margin-bottom: 1rem;">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
                    <div class="news-publisher">{publisher} • <span style="background: {bg}; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 0.7rem; color: {color};">{sentiment}</span></div>
                    <div style="color: #94a3b8; font-size:0.82rem;">{date_str}</div>
                </div>
                <a class="news-title" href="{link}" target="_blank">{title}</a>
            </div>
        """, unsafe_allow_html=True)

    if HAS_TEXTBLOB:
        st.caption("News data sourced from Yahoo Finance. Sentiment analysis powered by TextBlob.")
    else:
        st.caption("News data sourced from Yahoo Finance. Install 'textblob' to enable sentiment features.")
