"""Cached data access and logging helpers."""

import datetime
import io
import logging
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from breakout import run_backtest # This import is fine, no circular dependency with HEADERS


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
}


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
def load_ticker_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna(subset=["Open", "High", "Low", "Close"]) if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def load_nifty_history(period: str = "6mo") -> pd.DataFrame:
    try:
        df = yf.download("^NSEI", period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna(subset=["Close"]) if not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def run_backtest_cached(**kwargs):
    return run_backtest(**kwargs)


@st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
def get_sector_mapping(universe_type: str = "Nifty 500") -> dict:
    """Fetches a mapping of ticker to sector."""
    url = ""
    if universe_type == "Nifty 500":
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    elif universe_type == "Total Market (Cap Focused)":
        url = "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarketlist.csv"
    else:
        return {}  # Should not happen with current universe options

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        df = pd.read_csv(io.StringIO(res.text))
        sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
        sector_col = next((c for c in df.columns if "industry" in c.lower() or "sector" in c.lower()), None)
        if sym_col is None or sector_col is None:
            return {}
        return {f"{row[sym_col]}.NS": row[sector_col] for _, row in df.iterrows() if pd.notna(row[sym_col]) and pd.notna(row[sector_col])}
    except Exception as exc:
        logging.getLogger("AlphaScanner").error(f"Failed to fetch sector mapping for {universe_type}: {exc}")
        return {}


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
            df = yf.download(symbol, period="5d", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if len(df) >= 2:
                previous = float(df["Close"].iloc[-2])
                current = float(df["Close"].iloc[-1])
                change = (current - previous) / previous * 100
                output[name] = {"price": current, "change": round(change, 2)}
        except Exception:
            continue
    return output
