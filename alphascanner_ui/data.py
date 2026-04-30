"""Cached data access and logging helpers."""

import datetime
import io
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from breakout import run_backtest # This import is fine, no circular dependency with HEADERS


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/csv,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}

def _fetch_nse_csv(url: str) -> pd.DataFrame:
    """Robustly fetch CSV from NSE using a session handshake to bypass bot protection."""
    for attempt in range(3):
        try:
            session = requests.Session()
            # Visit home page first to get cookies
            session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
            res = session.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            if "text/csv" not in res.headers.get("Content-Type", "").lower() and "octet-stream" not in res.headers.get("Content-Type", "").lower():
                if "<html>" in res.text.lower():
                    raise ValueError("NSE blocked the request (Splash Page detected)")
            return pd.read_csv(io.StringIO(res.text))
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger = configure_logging()
                logger.error(f"Failed to fetch NSE CSV after 3 attempts: {e}")
                raise


def configure_logging() -> logging.Logger:
    """Ensure the app log directory and logger are ready before rendering."""
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=f"data/logs/alphascanner_{datetime.date.today()}.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger("AlphaScanner")


@st.cache_data(ttl=3600, show_spinner=False)
def load_ticker_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna(subset=["Open", "High", "Low", "Close"]) if not df.empty else pd.DataFrame()
    except Exception as e:
        logger = configure_logging()
        logger.error(f"Failed to load ticker history for {ticker}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def load_nifty_history(period: str = "6mo") -> pd.DataFrame:
    try:
        df = yf.download("^NSEI", period=period, progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna(subset=["Close"]) if not df.empty else pd.DataFrame()
    except Exception as e:
        logger = configure_logging()
        logger.error(f"Failed to load Nifty history: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def run_backtest_cached(**kwargs):
    return run_backtest(**kwargs)


@st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
def get_sector_mapping(universe_type: str = "Nifty 500") -> dict:
    """Fetches a mapping of ticker to sector."""
    urls = []
    if universe_type == "Nifty 500":
        urls = [
            "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
            "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
        ]
    elif universe_type == "Total Market (Cap Focused)":
        urls = [
            "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
            "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
            "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
            "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftymicrocap250list.csv",
        ]
    else:
        return {}  # Should not happen with current universe options

    mapping = {}
    for url in urls:
        try:
            df = _fetch_nse_csv(url)
            sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
            sector_col = next((c for c in df.columns if "industry" in c.lower() or "sector" in c.lower()), None)
            if sym_col and sector_col:
                batch_map = {
                    f"{row[sym_col]}.NS": row[sector_col] 
                    for _, row in df.iterrows() 
                    if pd.notna(row[sym_col]) and pd.notna(row[sector_col])
                }
                mapping.update(batch_map)
        except Exception as exc:
            logging.getLogger("AlphaScanner").warning(f"Sector segment {url} failed: {exc}")
    
    return mapping


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_fii_dii_data(_logger=None) -> dict:
    """NSE-compliant FII/DII fetcher with session handshake."""
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/reports/fii-dii",
    }

    try:
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        response = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            headers=headers,
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list):
                latest = data[0]
                return {
                    "date": latest.get("date", "N/A"),
                    "fii_net": float(latest.get("fiiNetValue", 0) or 0),
                    "dii_net": float(latest.get("diiNetValue", 0) or 0),
                    "fii_buy": float(latest.get("fiiBuyValue", 0) or 0),
                    "fii_sell": float(latest.get("fiiSellValue", 0) or 0),
                    "dii_buy": float(latest.get("diiBuyValue", 0) or 0),
                    "dii_sell": float(latest.get("diiSellValue", 0) or 0),
                }
    except Exception as exc:
        if _logger is not None:
            _logger.error("FII/DII Fetch Error: %s", exc)

    return {
        "date": "N/A",
        "fii_net": 0,
        "dii_net": 0,
        "fii_buy": 0,
        "fii_sell": 0,
        "dii_buy": 0,
        "dii_sell": 0,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_indices_performance() -> dict:
    symbols = {
        "Nifty 50": "^NSEI",
        "Bank Nifty": "^NSEBANK",
        "Sensex": "^BSESN",
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Dow Jones": "^DJI",
    }
    output = {}
    for name, symbol in symbols.items():
        try:
            df = yf.download(symbol, period="5d", progress=False, auto_adjust=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if len(df) >= 2:
                # Find the last non-NaN close
                close_series = df["Close"].dropna()
                if len(close_series) >= 2:
                    previous = float(close_series.iloc[-2])
                    current = float(close_series.iloc[-1])
                    change = (current - previous) / previous * 100
                    if pd.isna(change) or np.isinf(change):
                        change = 0.0
                    output[name] = {"price": current, "change": round(float(change), 2)}
        except Exception:
            continue
    return output
