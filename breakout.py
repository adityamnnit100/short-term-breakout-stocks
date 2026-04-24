"""
breakout.py  –  AlphaScanner PRO  |  Core scanning & back-test engine
Fixes in this revision
  - DB_PATH uses env-var / relative path instead of hard-coded /home/kumar/...
  - ltp always assigned before use (was undefined in some code paths)
  - All indicators vectorised; no redundant per-ticker recalculation
  - calculate_stochastic_rsi: explicit div/0 guard via .replace(0, np.nan)
  - detect_divergence: removed rolling argmin (FutureWarning in pandas >= 2.0)
  - run_scanner / run_backtest: robust multi-index column handling for yfinance >= 0.2
  - calculate_vwap: window=20 so value is non-NaN for 1-year history
  - get_nifty_500: case-insensitive symbol column detection
  - All error-return branches use consistent dict shape (_EMPTY_STATS)
"""

import os
import io
import time
import json
import sqlite3
import logging
import threading
import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Tuple, List, Dict
from threading import Lock

import numpy as np
import pandas as pd
import requests
import yfinance as yf
try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get(
    "ALPHASCANNER_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "breakout_history.db"),
)

_EMPTY_STATS: dict = {
    "scanned": 0, "universe": None, "universe_size": 0,
    "volume_fail": 0, "trend_fail": 0,
    "breakout_fail": 0, "momentum_fail": 0, "adx_fail": 0,
    "macd_fail": 0, "bb_fail": 0, "rs_fail": 0, "fakeout_trap": 0,
    "liquidity_fail": 0,
    "trending_sectors": [], "sector_sentiment": {},
    "market_breadth_50": 0.0, "scanner_type": None,
    "timeframe": "1d",
}


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
def _extract_symbols_from_index_csv(df: pd.DataFrame) -> list:
    sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
    if sym_col is None:
        return []
    return [
        f"{str(symbol).strip()}.NS"
        for symbol in df[sym_col].dropna()
        if str(symbol).strip()
    ]


def _fetch_index_symbols(urls: List[str], label: str) -> list:
    from alphascanner_ui.data import _fetch_nse_csv

    # Try Cache First (Expiry 24 hours) for Production Stability
    cache_key = f"symbols_{label.replace(' ', '_').lower()}"
    cached_data = get_system_cache(cache_key, expiry_hours=24)
    if cached_data:
        return json.loads(cached_data)

    logger = logging.getLogger("AlphaScanner.Engine")
    for url in urls:
        try:
            df = _fetch_nse_csv(url)
            symbols = _extract_symbols_from_index_csv(df)
            if symbols:
                logger.info("Fetched %s symbols for %s from %s", len(symbols), label, url)
                set_system_cache(cache_key, json.dumps(symbols))
                return symbols
            logger.warning("Symbol column not found for %s from %s", label, url)
        except Exception as exc:
            logger.warning("Failed to fetch %s from %s: %s", label, url, exc)
    return []


def get_nifty_500() -> list:
    urls = [
        "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    ]
    symbols = _fetch_index_symbols(urls, "Nifty 500")
    if symbols:
        return symbols

    logging.getLogger("AlphaScanner.Engine").warning("Failed to fetch Nifty 500, using fallback.")
    return [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS", "HDFCBANK.NS",
        "ICICIBANK.NS", "KOTAKBANK.NS", "HINDUNILVR.NS", "ITC.NS", "AXISBANK.NS",
    ]


def get_nifty_total_market() -> list:
    """Fetches the Nifty Total Market list (Nifty 500 + Microcaps)."""
    # NSE often restricts the single Total Market CSV. Combining Nifty 500 with
    # Microcap 250 is a stable reconstruction of the broader cap-focused universe.
    segments = {
        "Nifty 500": [
            "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
            "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
        ],
        "Nifty Microcap 250": [
            "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
            "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftymicrocap250list.csv",
        ],
    }

    all_tickers = set()
    fetched_counts = {}
    for label, urls in segments.items():
        symbols = _fetch_index_symbols(urls, label)
        fetched_counts[label] = len(symbols)
        all_tickers.update(symbols)

    if len(all_tickers) > 550:
        return sorted(list(all_tickers))

    logging.getLogger("AlphaScanner.Engine").error(
        "Nifty Total Market fetch only returned %s unique symbols (segment counts: %s). Falling back to Nifty 500.",
        len(all_tickers),
        fetched_counts,
    )
    return get_nifty_500()


def _build_market_context() -> dict:
    """Infer broad market bias from index moves and institutional flows."""
    try:
        from alphascanner_ui.data import fetch_indices_performance, fetch_fii_dii_data
        indices = fetch_indices_performance()
        fii_dii = fetch_fii_dii_data()
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").warning(f"Market context fetch failed: {exc}")
        return {
            "market_bias": "Neutral",
            "market_bias_score": 0.0,
            "fii_net": 0.0,
            "dii_net": 0.0,
            "nifty_change": 0.0,
            "bank_nifty_change": 0.0,
        }

    nifty_change = indices.get("Nifty 50", {}).get("change", 0.0)
    bank_change = indices.get("Bank Nifty", {}).get("change", 0.0)
    fii_net = float(fii_dii.get("fii_net", 0.0) or 0.0)
    dii_net = float(fii_dii.get("dii_net", 0.0) or 0.0)

    if nifty_change > 0 and bank_change > 0:
        bias = "Bullish"
    elif nifty_change < 0 and bank_change < 0:
        bias = "Bearish"
    elif nifty_change > 0 or bank_change > 0:
        bias = "Slightly Bullish"
    elif nifty_change < 0 or bank_change < 0:
        bias = "Slightly Bearish"
    else:
        bias = "Neutral"

    score = 0.0
    if bias == "Bullish":
        score += 0.8
    elif bias == "Slightly Bullish":
        score += 0.4
    elif bias == "Bearish":
        score -= 0.8
    elif bias == "Slightly Bearish":
        score -= 0.4

    score += 0.2 if fii_net > 0 else -0.2
    score += 0.2 if dii_net > 0 else -0.2

    return {
        "market_bias": bias,
        "market_bias_score": round(score, 2),
        "fii_net": fii_net,
        "dii_net": dii_net,
        "nifty_change": round(nifty_change, 2),
        "bank_nifty_change": round(bank_change, 2),
    }


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def is_market_open() -> bool:
    """Checks if the NSE market is currently open (9:15 AM - 3:30 PM IST, Mon-Fri)."""
    # IST is UTC + 5:30
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))

    # Weekends (Saturday=5, Sunday=6)
    if now_ist.weekday() >= 5:
        return False

    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= now_ist <= market_close


def get_last_market_close_utc() -> datetime:
    """Returns the UTC datetime of the most recent NSE market close."""
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))

    close_ist = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    if now_ist.weekday() >= 5:
        # Weekend: roll back to Friday close.
        close_ist -= timedelta(days=now_ist.weekday() - 4)
    elif now_ist < close_ist:
        # Before today's close: previous trading day, or Friday on Monday morning.
        close_ist -= timedelta(days=3 if now_ist.weekday() == 0 else 1)

    return close_ist - timedelta(hours=5, minutes=30)

def calculate_vwap(high, low, close, volume, window: int = 20):
    tp = (high + low + close) / 3
    vol_sum = volume.rolling(window=window).sum().replace(0, np.nan)
    return (tp * volume).rolling(window=window).sum() / vol_sum


def calculate_macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line, macd - signal_line


def calculate_bollinger_bands(close, window: int = 20, num_std: float = 2.0):
    sma = close.rolling(window=window).mean()
    std = close.rolling(window=window).std()
    return sma + std * num_std, sma, sma - std * num_std


def calculate_rsi(close, period: int = 14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100)
    rsi = rsi.mask((loss == 0) & (gain == 0), 50)
    return rsi


def calculate_atr(high, low, close, period: int = 14):
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calculate_adx(high, low, close, period: int = 14):
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    tr_smooth = tr.rolling(period).mean().replace(0, np.nan)
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = low.diff().clip(upper=0).abs()
    plus_di  = 100 * plus_dm.rolling(period).mean()  / tr_smooth
    minus_di = 100 * minus_dm.rolling(period).mean() / tr_smooth
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = (plus_di - minus_di).abs() / denom * 100
    return dx.rolling(period).mean()


def calculate_rvol(volume: pd.Series, window: int = 5) -> float:
    """Calculates Relative Volume (RVOL) compared to a short 5-day window.
    RVOL > 2.0 indicates significant institutional activity."""
    if len(volume) < window + 1:
        return 1.0
    avg_vol = volume.iloc[-(window+1):-1].mean()
    return float(volume.iloc[-1] / max(avg_vol, 1e-9))


def detect_breakaway_gap(df: pd.DataFrame, threshold_pct: float = 0.5) -> bool:
    """Detects if today's Open is significantly higher than yesterday's High.
    Crucial for identifying high-momentum Indian breakout plays."""
    if len(df) < 2:
        return False
    gap = (df["Open"].iloc[-1] - df["High"].iloc[-2]) / df["High"].iloc[-2] * 100
    return bool(gap >= threshold_pct)


def calculate_relative_strength(stock_close, index_close):
    """Calculates Relative Strength Rating vs Benchmark (0-100 scale logic)."""
    # Require at least 3 months (63 days) of data for a meaningful RS calculation
    if len(stock_close) < 63 or len(index_close) < 63:
        return 0.0

    # Weighted Performance calculation based on available history
    def get_perf(series):
        l = len(series)
        def calc_p(idx):
            if l >= abs(idx):
                denom = series.iloc[idx]
                return series.iloc[-1] / denom if denom != 0 else 1.0
            return None

        p1 = calc_p(-63) or 1.0
        p2 = calc_p(-126) or p1
        p3 = calc_p(-189) or p2
        p4 = calc_p(-252) or p3
        return (p1 * 0.4) + (p2 * 0.2) + (p3 * 0.2) + (p4 * 0.2)

    try:
        s_perf = get_perf(stock_close)
        i_perf = get_perf(index_close)
        rs_ratio = (s_perf / i_perf) * 100
    except Exception: return 0.0
    return round(rs_ratio, 1)


def calculate_stochastic_rsi(rsi, window: int = 14, smooth_k: int = 3, smooth_d: int = 3):
    min_rsi = rsi.rolling(window).min()
    max_rsi = rsi.rolling(window).max()
    denom = (max_rsi - min_rsi).replace(0, np.nan)      # FIX: guard div/0
    stoch = ((rsi - min_rsi) / denom * 100).fillna(50)
    k = stoch.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d


def detect_divergence(close, rsi, lookback: int = 20):
    """Improved divergence detection comparing current price action to recent structural peaks."""
    if len(close) < lookback + 5:
        return False, False

    # Find local min/max in the lookback window (excluding current candle)
    prev_min_price = close.iloc[-lookback:-1].min()
    prev_min_rsi = rsi.iloc[-lookback:-1].min()
    prev_max_price = close.iloc[-lookback:-1].max()
    prev_max_rsi = rsi.iloc[-lookback:-1].max()

    bull = bool(close.iloc[-1] < prev_min_price and rsi.iloc[-1] > prev_min_rsi)
    bear = bool(close.iloc[-1] > prev_max_price and rsi.iloc[-1] < prev_max_rsi)
    return bull, bear


def detect_vcp_tightness(close, window: int = 10):
    """Detects 'Tightness' in price action (Volatility Contraction)."""
    if len(close) < 50:
        return False
    recent_std = close.tail(window).std()
    hist_std = close.tail(50).std()
    return recent_std < (hist_std * 0.75)

def detect_minervini_template(df: pd.DataFrame, ltp: float) -> bool:
    """
    Implementation of Mark Minervini's Trend Template.
    Used by top momentum traders to ensure the stock is in a confirmed Stage 2 uptrend.
    """
    if len(df) < 200: return False
    close = df['Close']
    sma_50 = close.rolling(50).mean().iloc[-1]
    sma_150 = close.rolling(150).mean().iloc[-1]
    sma_200 = close.rolling(200).mean().iloc[-1]
    
    # 1. Price > 150 and 200 SMA
    c1 = ltp > sma_150 and ltp > sma_200
    # 2. 150 SMA > 200 SMA
    c2 = sma_150 > sma_200
    # 3. 200 SMA trending up for at least 1 month (22 sessions)
    sma_200_prev = close.rolling(200).mean().iloc[-22]
    c3 = sma_200 > sma_200_prev
    # 4. 50 SMA > 150 and 50 SMA > 200
    c4 = sma_50 > sma_150 and sma_50 > sma_200
    # 5. Price > 50 SMA
    c5 = ltp > sma_50
    # 6. Price at least 30% above 52-week low
    low_52 = close.tail(252).min()
    c6 = ltp >= (low_52 * 1.30)
    # 7. Price within 25% of 52-week high
    high_52 = close.tail(252).max()
    c7 = ltp >= (high_52 * 0.75)
    
    return all([c1, c2, c3, c4, c5, c6, c7])

def detect_inside_bar(df: pd.DataFrame) -> bool:
    """Detects an Inside Bar pattern (current candle is contained within previous candle)."""
    if len(df) < 2: return False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    return (last['High'] <= prev['High']) and (last['Low'] >= prev['Low'])

def detect_nr7(df: pd.DataFrame) -> bool:
    """Detects NR7 (Narrow Range 7) pattern – current range is the narrowest of the last 7 sessions."""
    if len(df) < 7: return False
    daily_ranges = (df['High'] - df['Low']).tail(7)
    # Check if current range is the minimum of the 7-day window
    return bool(daily_ranges.iloc[-1] == daily_ranges.min())

def calculate_base_weeks(df: pd.DataFrame, max_range_pct: float = 12.0) -> int:
    """Calculates consecutive weeks where price stayed within a tight percentage range prior to today."""
    if len(df) < 10:
        return 0
    weeks = 0
    # Check backwards in 5-day increments, excluding the current candle
    for w in range(1, (len(df) // 5)):
        period = df.iloc[-(w * 5) - 1 : -1]
        p_max = period["High"].max()
        p_min = period["Low"].min()
        if p_min > 0 and ((p_max - p_min) / p_min) * 100 <= max_range_pct:
            weeks = w
        else:
            break
    return weeks

def calculate_consolidation_days(df: pd.DataFrame, max_range_pct: float = 10.0) -> int:
    """Calculates consecutive trading days where price stayed within a tight range prior to today."""
    if len(df) < 5:
        return 0
    days = 0
    # Check backwards day by day from yesterday (excluding current incomplete candle)
    for d in range(1, len(df) - 1):
        period = df.iloc[-(d + 1) : -1]
        p_max = period["High"].max()
        p_min = period["Low"].min()
        if p_min > 0 and ((p_max - p_min) / p_min) * 100 <= max_range_pct:
            days = d
        else:
            break
    return days

def detect_volume_dryup(volume: pd.Series, window: int = 30, threshold: float = 0.7) -> bool:
    """Detects 'Volume Dry-up' (Supply exhaustion) compared to recent average."""
    if len(volume) < window:
        return False
    avg_vol = volume.rolling(window).mean().iloc[-2]
    return float(volume.iloc[-1]) < (avg_vol * threshold)

def detect_volume_surge(volume: pd.Series, window: int = 10, threshold: float = 3.0) -> bool:
    """Detects 'Volume Surge' (Institutional entry) compared to short-term average."""
    if len(volume) < window:
        return False
    avg_vol_short = volume.rolling(window).mean().iloc[-2]
    # For Indian markets, also check if volume is above 30-day average for confirmation
    avg_vol_long = volume.rolling(30).mean().iloc[-2]
    return float(volume.iloc[-1]) >= (avg_vol_short * threshold) or float(volume.iloc[-1]) >= (avg_vol_long * 1.5)

def detect_candlestick_pattern(df: pd.DataFrame) -> str:
    """Detects simple candlestick patterns for high-conviction entries."""
    if len(df) < 2: return "Neutral"
    last = df.iloc[-1]
    prev = df.iloc[-2]
    # Fetch third candle for multi-bar patterns like Morning Star
    prev2 = df.iloc[-3] if len(df) >= 3 else None

    body = last['Close'] - last['Open']
    abs_body = abs(body)
    range_ = max(last['High'] - last['Low'], 1e-9)
    upper_wick = last['High'] - max(last['Open'], last['Close'])
    lower_wick = min(last['Open'], last['Close']) - last['Low']

    # 1. Morning Star (3-candle bullish reversal)
    if prev2 is not None:
        prev2_body = prev2['Open'] - prev2['Close']
        if (prev2_body > 0 and # 1st: Significant Bearish
            abs(prev['Open'] - prev['Close']) < prev2_body * 0.5 and # 2nd: Small body "star"
            body > 0 and # 3rd: Bullish
            last['Close'] > (prev2['Open'] + prev2['Close']) / 2): # 3rd: Closes > 50% of 1st
            return "Morning Star"

    # 2. Shooting Star (Bearish reversal - small body, long upper wick)
    # Occurs when buyers push price to new highs but sellers force a low close
    if upper_wick > 2 * abs_body and lower_wick < 0.2 * range_ and last['High'] > prev['High']:
        return "Shooting Star"

    # 3. Hammer / Bullish Pin Bar
    if lower_wick > 2 * abs_body and upper_wick < 0.1 * range_:
        return "Bullish Hammer"

    # 4. Bullish Engulfing
    if body > 0 and prev['Close'] < prev['Open'] and last['Close'] > prev['Open'] and last['Open'] < prev['Close']:
        return "Bullish Engulfing"

    return "Strong Bullish" if (body > 0 and abs_body > 0.8 * range_) else "Neutral"

# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------

def detect_52week_high(df, proximity_pct: float = 2.0) -> bool:
    if len(df) < 252:
        return False
    return float(df["Close"].iloc[-1]) >= float(df["High"].iloc[-252:-1].max()) * (1 - proximity_pct / 100)


def detect_range_breakout(df, lookback: int = 20):
    h = float(df["High"].iloc[-lookback:-1].max())
    l = float(df["Low"].iloc[-lookback:-1].min())
    # Launch Zone: Price is within 2% of the high but hasn't crossed it significantly yet
    return h * 0.98 <= float(df["Close"].iloc[-1]) <= h * 1.005, h, l


def detect_trendline_breakout(df, lookback: int = 30) -> bool:
    if len(df) < lookback:
        return False
    vals = df["Close"].iloc[-lookback:].values
    x = np.arange(len(vals))
    c = np.polyfit(x, vals, 1)
    return bool(vals[-1] > c[0] * x[-1] + c[1])


def detect_flag_pattern(df, lookback: int = 7, pole_lookback: int = 15) -> bool:
    if len(df) < pole_lookback + lookback:
        return False
    pole = df["Close"].iloc[-pole_lookback - lookback: -lookback].values
    flag = df["Close"].iloc[-lookback:].values
    pole_up = pole[-1] > pole[0] * 1.03
    flag_range = (flag.max() - flag.min()) / max(abs(float(flag[0])), 1e-9)
    flag_ok = flag_range < 0.05
    breakout = len(flag) > 1 and flag[-1] > flag[:-1].max() * 1.005
    return pole_up and flag_ok and breakout


def detect_cup_handle(df, lookback: int = 60) -> bool:
    if len(df) < lookback:
        return False
    vals = df["Close"].iloc[-lookback:].values
    low_idx = int(np.argmin(vals))
    if low_idx < 20 or low_idx > lookback - 20:
        return False
    cup_h = vals[-1] - vals[low_idx]
    handle = (vals[-5:].max() - vals[-5:].min()) < cup_h * 0.2 if len(vals) >= 5 else False
    return vals[low_idx] < vals[0] * 0.97 and vals[-1] > vals[low_idx] * 1.02 and handle


def detect_rounding_bottom(df, lookback: int = 40) -> bool:
    """Detects a U-shaped recovery using quadratic curve fitting."""
    if len(df) < lookback:
        return False
    vals = df["Close"].iloc[-lookback:].values
    x = np.arange(len(vals))
    coeffs = np.polyfit(x, vals, 2)
    # Positive x^2 coefficient indicates a U-shape (concave up)
    is_u_shape = coeffs[0] > 0.001
    mid_val = vals[len(vals) // 2]
    # Ensure the middle is lower than the start and end
    is_low_center = mid_val < vals[0] and mid_val < vals[-1]
    breakout = vals[-1] >= np.max(vals) * 0.99
    return is_u_shape and is_low_center and breakout


def detect_inverted_head_shoulders(df, lookback: int = 60) -> bool:
    """Detects three troughs where the middle one is the deepest."""
    if len(df) < lookback:
        return False
    lows = df["Low"].iloc[-lookback:].values
    third = len(lows) // 3
    ls_min, head_min, rs_min = np.min(lows[:third]), np.min(lows[third:2*third]), np.min(lows[2*third:])
    # Head is lowest, shoulders are relatively symmetrical (within 5%)
    structure_ok = head_min < ls_min and head_min < rs_min
    symmetry_ok = abs(ls_min - rs_min) / max(ls_min, 1e-9) < 0.05
    neckline = np.max(df["High"].iloc[-lookback:-1].values)
    return structure_ok and symmetry_ok and float(df["Close"].iloc[-1]) > neckline


def detect_triangle_breakout(df, lookback: int = 12) -> bool:
    if len(df) < lookback:
        return False
    highs = df["High"].iloc[-lookback:].values
    lows  = df["Low"].iloc[-lookback:].values
    conv  = (highs[-2] < highs[0]) and (lows[-2] > lows[0])
    bo    = len(highs) > 1 and float(df["Close"].iloc[-1]) > highs[:-1].max()
    return conv and bo


def detect_support_resistance(df, lookback: int = 50):
    h = float(df["High"].iloc[-lookback:].max())
    l = float(df["Low"].iloc[-lookback:].min())
    c = float(df["Close"].iloc[-1])
    return c > h * 0.98, c < l * 1.02, h, l


def _is_finite(*values) -> bool:
    return all(pd.notna(value) and np.isfinite(float(value)) for value in values)


def _scanner_quality_profile(scanner_type: str, universe: str) -> dict:
    """Central quality gates so Nifty 500 and cap-focused scans stay consistent."""
    is_total_market = universe == "Total Market (Cap Focused)"
    is_pre_breakout = scanner_type == "Pre-Breakout"
    is_pullback = scanner_type == "Pullback"

    return {
        "rs_floor": (
            45 if is_total_market and is_pre_breakout else  # RELAXED
            50 if is_pullback else                          # Moderate for pullbacks
            50 if is_total_market else                      # RELAXED
            50 if is_pre_breakout else                      # RELAXED
            55                                               # RELAXED
        ),
        "adx_min": 20 if is_pullback else (10 if is_pre_breakout else 16),
        "breakout_buffer_pct": 0.3 if is_total_market else 0.2,  # REALISTIC: Recent breakouts
        "breakout_upper_buffer_pct": 0.50,
        "pre_breakout_upper_buffer_pct": 0.20,  # For consolidating near high
        "min_avg_volume": 75_000 if is_total_market else 50_000,
        "min_price": 20 if is_total_market else 10,
        "max_daily_extension_pct": 7.0 if is_total_market else 8.0,
        "min_close_position": 0.55 if is_pre_breakout else 0.65,
        "accumulation_signal_count_min": 2,
    }


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

def _extract_ticker(data, ticker):
    """Safe multi-index extraction for yfinance >= 0.2."""
    if isinstance(data.columns, pd.MultiIndex):
        return data.xs(ticker, axis=1, level=1).dropna(how="all")
    return data.copy()


# =========================
# UPDATED BREAKOUT SCANNER
# Key Fixes Applied:
# - Relaxed RSI & RS filters
# - Strong candle confirmation
# - Actual breakout logic added
# - ADX rising condition
# - Pattern filter relaxed
# - Better logging
# - Added Candlestick Sentiment & Actionable Advice
# - Safer RS calculation (alignment fix)
# =========================

# Replace ONLY run_scanner() in your breakout.py with this version

def prefetch_metadata(tickers: List[str]):
    """Optimized batch fetching of fundamental metadata to populate cache."""
    logger = logging.getLogger("AlphaScanner.Engine")
    # Only fetch if cache is missing OR older than 24 hours
    to_fetch = [t for t in tickers if get_metadata_cache(t, expiry_hours=24)[0] is None]

    if not to_fetch:
        logger.info("Metadata cache is up to date. Skipping prefetch.")
        return

    logger.info(f"Prefetching metadata for {len(to_fetch)} tickers...")

    def _fetch_worker(ticker):
        try:
            t_obj = yf.Ticker(ticker)
            # fast_info is high performance; only hit .info if absolutely necessary
            m_cap = t_obj.fast_info.get('marketCap', 0)
            roe = 0.0
            try:
                roe = t_obj.info.get('returnOnEquity', 0.0)
            except: pass
            update_metadata_cache(ticker, m_cap / 10_000_000, roe)
        except Exception:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        executor.map(_fetch_worker, to_fetch)


_METADATA_WORKER_THREAD = None
_METADATA_WORKER_LOCK = Lock()

def _metadata_worker_loop(interval_hours: int = 8):
    """Background loop that keeps the fundamental metadata fresh while the app is idle."""
    logger = logging.getLogger("AlphaScanner.Engine")
    logger.info("Background metadata worker starting...")
    while True:
        try:
            # Target the broadest universe to ensure cache coverage
            tickers = get_nifty_total_market()
            prefetch_metadata(tickers)
            logger.info(f"Background cache refresh complete for {len(tickers)} symbols.")
        except Exception as e:
            logger.error(f"Metadata background worker error: {e}")
        time.sleep(interval_hours * 3600)

def start_background_metadata_worker():
    """Initializes the metadata worker thread if it is not already running."""
    global _METADATA_WORKER_THREAD
    with _METADATA_WORKER_LOCK:
        if _METADATA_WORKER_THREAD is None or not _METADATA_WORKER_THREAD.is_alive():
            _METADATA_WORKER_THREAD = threading.Thread(
                target=_metadata_worker_loop,
                daemon=True,
                name="MetadataBackgroundWorker"
            )
            _METADATA_WORKER_THREAD.start()

def _process_single_ticker(
    ticker: str,
    data: pd.DataFrame,
    nifty_close: pd.Series,
    vol_thresh: float,
    rsi_min: float,
    rsi_max: float,
    dist_thresh: float,
    apply_market_cap_filter: bool,
    min_mkt_cap_cr: float,
    max_mkt_cap_cr: float,
    scanner_type: str,
    universe: str,
    timeframe: str,
    sector_map: Optional[dict],
    trending_sectors: set,
    sector_sentiment_map: dict,
    market_context: dict,
    stats: dict,
    stats_lock: Lock
) -> Optional[dict]:
    """Internal worker to process a single ticker's logic."""
    try:
        df = _extract_ticker(data, ticker)
        df = df.dropna(subset=["Close", "High", "Low", "Open", "Volume"])

        if len(df) < 200:
            return None

        with stats_lock:
            stats["scanned"] += 1

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        vol = df["Volume"]

        # Align RS safely
        close_aligned, nifty_aligned = close.align(nifty_close, join="inner")
        if close_aligned.empty or nifty_aligned.empty:
            return None

        # Indicators
        sma_200 = close.rolling(200).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1]
        ema_20 = close.ewm(span=20, adjust=False).mean().iloc[-1]

        avg_vol = vol.rolling(30).mean().iloc[-2]
        rsi_series = calculate_rsi(close)
        rsi = rsi_series.iloc[-1]
        adx_series = calculate_adx(high, low, close)
        adx = adx_series.iloc[-1]
        adx_prev = adx_series.iloc[-2]
        macd, macd_sig, macd_hist = calculate_macd(close)
        upper_bb, mid_bb, lower_bb = calculate_bollinger_bands(close)
        vwap = calculate_vwap(high, low, close, vol).iloc[-1]
        
        # Short-term Professional Features
        rvol = calculate_rvol(vol) if not vol.empty else 1.0
        is_breakaway = detect_breakaway_gap(df) if len(df) >= 2 else False

        # Stochastic RSI implementation (Filter 10)
        stoch_k_ser, _ = calculate_stochastic_rsi(rsi_series)
        stoch_k = stoch_k_ser.iloc[-1] if not stoch_k_ser.empty else 50.0
        stoch_neutral = 20 <= stoch_k <= 80

        ltp = float(close.iloc[-1])
        open_price = float(df["Open"].iloc[-1])
        day_range = float(high.iloc[-1] - low.iloc[-1])
        body = abs(ltp - open_price)
        relative_close = (ltp - float(low.iloc[-1])) / max(day_range, 1e-9)
        daily_pcnt = (ltp - open_price) / max(open_price, 1e-9) * 100
        
        # Extension Check: Distance from EMA20
        dist_from_ema = (ltp - ema_20) / max(ema_20, 1e-9) * 100
        is_stretched = dist_from_ema > 5.0  # Avoid entry if > 5% away from 20-EMA

        # Hard reject stretched breakouts for short-term entries.
        if is_stretched:
            return None

        quality_profile = _scanner_quality_profile(scanner_type, universe)

        if not _is_finite(ltp, avg_vol, sma_200, sma_50, ema_20, rsi, adx, adx_prev, vwap):
            return None

        if ltp < quality_profile["min_price"] or avg_vol < quality_profile["min_avg_volume"]:
            with stats_lock:
                stats["liquidity_fail"] += 1
            return None

        # MA Slopes (Filter 11: MAs rising over last 3 days for responsiveness)
        ema_20_prev_val = close.ewm(span=20, adjust=False).mean().iloc[-3]
        sma_50_prev_val = close.rolling(50).mean().iloc[-3]
        ma_slope_bull = (ema_20 > ema_20_prev_val) and (sma_50 > sma_50_prev_val)

        ticker_sector = sector_map.get(ticker, "N/A") if sector_map else "N/A"
        sector_score = sector_sentiment_map.get(ticker_sector, 5.0)
        is_tight = detect_vcp_tightness(close)
        is_inside_bar = detect_inside_bar(df)
        is_nr7 = detect_nr7(df)
        base_weeks = calculate_base_weeks(df)
        consol_days = calculate_consolidation_days(df)
        is_dry = detect_volume_dryup(vol)

        # Accumulation signal counter for pre-breakout
        accum_signals_count = sum([
            is_tight, is_dry, is_inside_bar, is_nr7,
            base_weeks >= 2, consol_days >= 5
        ])

        # GRANULAR SETUP SCORE (0-10) for Pre-Breakout Ranking
        recent_std = close.tail(10).std()
        hist_std = close.tail(50).std()
        tightness_ratio = (recent_std / hist_std) if hist_std > 0 else 1.0
        # 1. RSI Accumulation Score: Centered at 52.5 (Max 5 pts)
        rsi_acc_score = max(0, 5 - abs(rsi - 52.5) / 2.5) if (40 <= rsi <= 65) else 0
        # 2. Tightness Score: Max points if ratio <= 0.5 (Max 5 pts)
        t_acc_score = max(0, min(5.0, (0.75 - tightness_ratio) / 0.25 * 5)) if tightness_ratio < 0.75 else 0
        setup_score = round(min(10.0, rsi_acc_score + t_acc_score), 1)

        # Volume Surge is validated only if the stock belongs to a trending/outperforming sector
        is_surge = detect_volume_surge(vol)
        if sector_map and ticker_sector != "N/A":
            # For Pre-Breakout, volume surge is a bonus but not required
            # For Breakout, it's part of the verification
            if scanner_type == "Breakout":
                is_surge = is_surge and (ticker_sector in trending_sectors)
            else:
                # Pre-breakout just needs ANY vol confirmation or pattern
                is_surge = is_surge or detect_volume_dryup(vol)

        # Volume filter - use appropriate threshold
        vol_ratio = float(vol.iloc[-1]) / max(avg_vol, 1)
        # For Pre-Breakout, relax volume requirement: just need 0.5x avg in tight setup
        if scanner_type == "Pre-Breakout" and (is_tight or is_dry):
            min_vol_ratio = max(0.5, float(vol_thresh) * 0.5)  # Softer requirement for tight patterns
        elif scanner_type == "Pullback":
            min_vol_ratio = 0.4  # We WANT low volume on a pullback (supply dry-up)
        else:
            min_vol_ratio = float(vol_thresh)

        # Trend filter: require strong short-term momentum, but allow new breakouts
        # where the 50-day average is still catching up to the 200-day average.
        trend_stack_ok = (ema_20 > sma_50) and (sma_50 > sma_200)
        is_minervini_leader = detect_minervini_template(df, ltp)
        
        partial_trend_ok = (ema_20 > sma_50) and (sma_50 >= sma_200 * 0.96)
        if scanner_type == "Breakout":
            # Breakouts may occur before the long-term stack is fully aligned.
            trend_ok = (
                (is_minervini_leader)
                or (trend_stack_ok and (ltp > ema_20 * 0.98))
                or (partial_trend_ok and (ltp > ema_20 * 0.99) and adx > 18)
            )
        elif scanner_type == "Pre-Breakout":
            # Pre-Breakouts can form while the trend stack is building.
            trend_ok = (
                (trend_stack_ok and (ltp > ema_20 * 0.985))
                or (ema_20 > sma_50 and ltp > ema_20 * 0.98)
            )
        else:  # Pullback
            trend_ok = trend_stack_ok and (ltp > ema_20 * 0.99)

        if not trend_ok:
            with stats_lock: stats["trend_fail"] += 1
            return None

        # Filter 3: RSI Momentum
        if not (rsi_min <= rsi <= rsi_max):
            with stats_lock: stats["momentum_fail"] += 1
            return None

        # RS filter
        rs_rating = calculate_relative_strength(close_aligned, nifty_aligned)
        rs_floor = quality_profile["rs_floor"]

        if rs_rating < rs_floor and not (rs_rating == 0 and rsi > 70):
            with stats_lock: stats["rs_fail"] += 1
            return None

        # ADX Threshold (Filter 5)
        adx_min = quality_profile["adx_min"]
        if not (adx > adx_min):
            with stats_lock: stats["adx_fail"] += 1
            return None

        adx_rising = adx > adx_prev

        # Breakout logic (Filter 6)
        prev_h20 = float(high.iloc[-21:-1].max())
        prev_h52 = float(high.iloc[-252:-1].max())
        breakout_buffer = 1 + quality_profile["breakout_buffer_pct"] / 100
        breakout_upper = 1 + quality_profile["breakout_upper_buffer_pct"] / 100
        pre_upper_buffer = 1 + quality_profile["pre_breakout_upper_buffer_pct"] / 100

        # Use appropriate upper buffer based on scanner type
        upper_buffer = breakout_upper if scanner_type == "Breakout" else pre_upper_buffer
        near_20d = prev_h20 * (1 - dist_thresh / 100) <= ltp <= prev_h20 * upper_buffer
        near_52w = prev_h52 * (1 - dist_thresh / 100) <= ltp <= prev_h52 * upper_buffer
        broke_20d = ltp >= prev_h20 * breakout_buffer
        broke_52w = ltp >= prev_h52 * breakout_buffer

        # Initialize flags to avoid UnboundLocalError
        is_breaking_out = False
        is_consolidating_near_20d = False
        is_consolidating_near_52w = False
        actual_breakout_condition_met = False
        is_pullback_to_ema = False

        if scanner_type == "Breakout":
            is_breaking_out = broke_20d or broke_52w
            actual_breakout_condition_met = is_breaking_out
        elif scanner_type == "Pullback":
            # Pullback logic: Price is within 1.5% of EMA 20 and volume is decreasing
            is_near_ema20 = (ema_20 * 0.99 <= ltp <= ema_20 * 1.015)
            # Confirmation: Previous candle was further from EMA20 (showing a return to mean)
            was_stretched = (df["Close"].iloc[-5:-1].max() > ema_20 * 1.03)
            is_pullback_to_ema = is_near_ema20 and was_stretched
            actual_breakout_condition_met = is_pullback_to_ema
        else: # Pre-Breakout (default)
            # Pre-breakout is a tight, constructive base near resistance, not a late chase after expansion.
            is_consolidating_near_20d = near_20d and not broke_20d
            is_consolidating_near_52w = near_52w and not broke_52w
            is_breaking_out = broke_20d or broke_52w
            # Pre-breakout: Need at least 1 accumulation signal (tight base, vol dry-up, inside bar, NR7, base weeks, or consol days)
            # OR if RSI + ADX are both strong, relax requirement
            has_strong_momentum = (rsi >= 70) and (adx > 20)
            has_strong_setup = (rsi <= 55) and (adx > 15)  # Accumulation zone  + momentum
            accumulation_signal = (accum_signals_count >= 1) or has_strong_momentum or has_strong_setup
            actual_breakout_condition_met = (
                (is_consolidating_near_20d or is_consolidating_near_52w)
                and accumulation_signal
            )

        # Fakeout detection: price breaks resistance but volume is below threshold
        is_fakeout = is_breaking_out and vol_ratio < min_vol_ratio

        # Check breakout condition early - core requirement
        if not actual_breakout_condition_met:
            with stats_lock: stats["breakout_fail"] += 1
            return None

        # Filter 4: Candle quality. Breakouts need expansion; pre-breakouts can be quieter but must close constructively.
        if day_range == 0:
            return None
        body_ratio = body / day_range
        if scanner_type == "Pre-Breakout" and relative_close < quality_profile["min_close_position"]:
            return None

        # Anti-chase filter: especially important in small/midcap scans where late entries get punished.
        if daily_pcnt > quality_profile["max_daily_extension_pct"]:
            return None

        candle_sentiment = detect_candlestick_pattern(df)

        # Trend Intensity based on MA Slopes and ADX
        trend_slope = (ema_20 - ema_20_prev_val) / max(ema_20_prev_val, 1e-9) * 100
        trend_intensity = "Strong" if (adx > 25 and trend_slope > 0.5) else ("Moderate" if adx > 20 else "Weak")

        # MACD confirmation (Filter 7)
        macd_bull = macd.iloc[-1] > macd_sig.iloc[-1] and macd_hist.iloc[-1] > 0
        if not macd_bull:
            with stats_lock: stats["macd_fail"] += 1

        # BB & VWAP confirmation (Filters 8 & 9)
        bb_upper_zone = ltp >= (mid_bb.iloc[-1] + (upper_bb.iloc[-1] - mid_bb.iloc[-1]) * 0.5)
        bb_breakout = ltp > upper_bb.iloc[-1]
        above_vwap = ltp > vwap
        bb_bull = bb_upper_zone or bb_breakout
        if not bb_bull:
            with stats_lock: stats["bb_fail"] += 1

        bull_div, bear_div = detect_divergence(close, rsi_series)
        # Calculate risk management levels for short-term trading
        atr = calculate_atr(high, low, close).iloc[-1]
        atr = float(atr) if not pd.isna(atr) and atr > 0 else ltp * 0.015

        # Support levels for risk management
        support1 = float(mid_bb.iloc[-1]) if pd.notna(mid_bb.iloc[-1]) else ltp * 0.95
        support2 = float(sma_200) if pd.notna(sma_200) else ltp * 0.90

        # Position sizing: Risk 1% of capital per trade
        risk_per_trade = 0.01  # 1% of capital
        stop_loss_distance = atr * 1.5  # 1.5 ATR stop
        position_size = risk_per_trade / (stop_loss_distance / ltp) if stop_loss_distance > 0 else 0

        # Profit targets for short-term scalping
        tp1 = ltp + (atr * 1.0)  # Quick profit at 1 ATR
        tp2 = ltp + (atr * 3.0)  # Main target at 3 ATR
        tp3 = ltp + (atr * 5.0)  # Extended target at 5 ATR

        # Stop loss levels
        sl1 = ltp - (atr * 1.5)  # Primary stop at 1.5 ATR
        sl2 = support1 if support1 < sl1 else sl1 * 0.98  # Support-based stop

        # Fundamental Check
        mkt_cap_cr, roe = 0.0, 0.0
        cached_mkt_cap, cached_roe = get_metadata_cache(ticker)

        if cached_mkt_cap is not None:
            mkt_cap_cr, roe = cached_mkt_cap, cached_roe
        else:
            # Fallback if prefetch missed it (should be rare)
            try:
                t_obj = yf.Ticker(ticker)
                mkt_cap_cr = t_obj.fast_info.get('marketCap', 0) / 10_000_000
                roe = 0.0 # Skip heavy .info in the hot loop
            except: pass

        if apply_market_cap_filter and mkt_cap_cr < min_mkt_cap_cr:
             return None

        if apply_market_cap_filter and max_mkt_cap_cr > 0 and mkt_cap_cr > max_mkt_cap_cr:
             return None

        # Market cap sanity check (avoid micro-cap garbage)
        if mkt_cap_cr > 0 and mkt_cap_cr < 10:  # <10Cr stocks are too illiquid
             return None

        patterns = []
        if detect_flag_pattern(df): patterns.append("Flag")
        if detect_triangle_breakout(df): patterns.append("Triangle")
        if detect_cup_handle(df): patterns.append("CupHandle")
        if detect_rounding_bottom(df): patterns.append("Rounding")
        if detect_inverted_head_shoulders(df): patterns.append("Inv-H&S")
        if is_inside_bar: patterns.append("Inside Bar")
        if is_nr7: patterns.append("NR7")
        if is_tight: patterns.append("VCP-Tight")
        if is_dry: patterns.append("Vol-Dryup")
        if is_surge: patterns.append("Vol-Surge")
        if base_weeks >= 4:
            patterns.append(f"Base-{base_weeks}W")

        # Standardized 11-Filter Confluence Scoring (0-10)
        score = 0.0
        score += 1.5 if trend_stack_ok else 0.0      # Filter 1
        score += 1.0 if vol_ratio >= 1.5 else 0.5    # Filter 2 (Partial for lower vol in Pre-Breakout)
        score += 1.0 if (rsi_min <= rsi <= rsi_max) else 0.0 # Filter 3
        score += 1.5 if relative_close >= 0.7 else 0.0 # Filter 4 (High quality close)
        score += 1.0 if (adx > 20 or (scanner_type == "Pre-Breakout" and adx > adx_min)) else 0.0 # Filter 5
        score += 1.0 if actual_breakout_condition_met else 0.0 # Filter 6
        score += 1.0 if macd_bull else 0.0           # Filter 7
        score += 1.0 if bb_bull else 0.0             # Filter 8
        score += 0.5 if (pd.notna(vwap) and above_vwap) else 0.0  # Filter 9
        score += 0.5 if stoch_neutral else 0.0       # Filter 10
        score += 1.0 if ma_slope_bull else 0.0       # Filter 11
        score += 0.5 if adx_rising else 0.0
        score += 1.5 if is_minervini_leader else 0.0 # Pro Leader Bonus
        score += 1.5 if (pd.notna(rvol) and rvol >= 2.5) else 0.5 # Bonus for high RVOL
        score += 1.0 if (pd.notna(is_breakaway) and is_breakaway) else 0.0

        # Pattern Bonuses
        if is_tight and is_dry: score += 1.5
        if is_inside_bar and is_nr7: score += 2.0
        if rs_rating >= 90: score += 1.0
        
        if is_fakeout or is_stretched:
            score -= 3.0
            patterns.append("Fakeout-Trap")
            with stats_lock: stats["fakeout_trap"] += 1

        strength = min(10.0, max(0.0, round(score, 1)))

        # Sector Sentiment Factor (Bonus/Penalty)
        if sector_score >= 8.0:
            strength += 1.5
            if rs_rating >= 85: # Synergistic bonus for Sentiment + High RS
                strength += 1.5
        elif sector_score <= 4.0:
            strength -= 1.0

        if is_fakeout:
            strength = min(strength, 3.5) # Drastic reduction for low-volume traps

        strength = min(10.0, round(strength, 1))

        # FINAL TRIGGER: Simple and clean (no redundancy)
        if scanner_type == "Breakout":
            # Breakout requires: actual break + volume confirmation
            if not (is_breaking_out and (vol_ratio >= min_vol_ratio)):
                with stats_lock: stats["breakout_fail"] += 1
                return None

        market_score = float(market_context.get("market_bias_score", 0.0))
        if scanner_type == "Pre-Breakout":
            market_score *= 0.5
        strength += market_score
        strength = min(10.0, max(0.0, round(strength, 1)))
        # Pre-Breakout and Pullback validated via actual_breakout_condition_met above

        return {
            "Ticker": ticker,
            "Type": scanner_type,
            "LTP": round(ltp, 2),
            "ATR": round(atr, 2),
            "RSI": round(rsi, 1),
            "RVOL": round(rvol, 1),
            "EMA_Dist": f"{dist_from_ema:.1f}%",
            "RS_Rating": rs_rating,
            "ROE": round(roe * 100, 1),
            "Mkt_Cap_Cr": round(mkt_cap_cr, 1),
            "Setup_Score": setup_score if scanner_type == "Pre-Breakout" else 0.0,
            "Sector": ticker_sector,
            "Sector_Score": sector_score,
            "Base_Weeks": base_weeks,
            "Consol_Days": consol_days,
            "Vol_x": round(vol_ratio, 1),
            "MACD": "✅" if macd_bull else "—",
            "BB": "✅" if bb_bull else "—",
            "VWAP": "✅" if above_vwap else "—",
            "Divergence": "Bullish" if bull_div else ("Bearish" if bear_div else "—"),
            "Vol_Spike": "🔥 SURGE" if is_surge else ("✅" if vol_ratio >= min_vol_ratio else "—"),
            "_Support1": round(float(mid_bb.iloc[-1]), 2) if pd.notna(mid_bb.iloc[-1]) else round(ltp * 0.95, 2),
            "_Support2": round(float(sma_200), 2) if pd.notna(sma_200) else round(ltp * 0.90, 2),
            "_Resistance": round(float(resistance), 2),
            "Market_Bias": market_context.get("market_bias", "Neutral"),
            "Macro_Score": round(market_context.get("market_bias_score", 0.0), 2),
            "Signal_Strength": strength,
            "Trend": trend_intensity,
            "Candle": "Consolidating" if daily_pcnt < 1.5 else candle_sentiment,
            "Action": (
                "AVOID: Fakeout" if is_fakeout else
                "⚠️ STRETCHED" if is_stretched else
                "💎 VCP Setup" if (scanner_type == "Pre-Breakout" and is_tight and is_dry) else
                "🛡️ EMA Support" if (scanner_type == "Pullback" and is_pullback_to_ema) else
                "🎯 Near Breakout" if (scanner_type == "Pre-Breakout" and (is_consolidating_near_20d or is_consolidating_near_52w)) else
                "⚡ SuperCoil" if (is_inside_bar and is_nr7) else
                "🏆 Market Leader" if is_minervini_leader else
                "🚀 Breakaway" if (is_breakaway and rvol > 2) else
                "🌀 Tight Coil" if (is_inside_bar and is_tight) else
                "🚀 Ready to Pop" if (strength >= 7.5 and is_tight) else "👀 Monitoring"
            ),
            "Pattern": ", ".join(patterns) if patterns else (
                "52W Breakout" if broke_52w else
                "20D Breakout" if broke_20d else
                "Near 52W" if is_consolidating_near_52w else
                "Near 20D"
            ),
        }
    except Exception as e:
        logging.getLogger("AlphaScanner.Engine").error(f"Error in {ticker}: {str(e)}")
        return None

def run_scanner(
    vol_thresh: float = 1.5,
    rsi_min: float = 50,
    rsi_max: float = 90,
    dist_thresh: float = 1.5,
    min_mkt_cap_cr: float = 0.0,
    max_mkt_cap_cr: float = 0.0,
    scanner_type: str = "Breakout", # Added scanner_type
    universe: str = "Nifty 500",
    timeframe: str = "1d",
    sector_map: Optional[dict] = None,
    progress_callback=None,
):
    apply_market_cap_filter = min_mkt_cap_cr > 0 or max_mkt_cap_cr > 0

    if universe == "Total Market (Cap Focused)":
        tickers = get_nifty_total_market()
    else:
        tickers = get_nifty_500()

    stats = _EMPTY_STATS.copy()
    stats["universe"] = universe
    stats["universe_size"] = len(tickers)
    stats["scanner_type"] = scanner_type
    stats["timeframe"] = timeframe
    market_context = _build_market_context()
    stats["market_bias"] = market_context.get("market_bias")
    stats["market_bias_score"] = market_context.get("market_bias_score")
    stats["fii_net"] = market_context.get("fii_net")
    stats["dii_net"] = market_context.get("dii_net")
    stats["nifty_change"] = market_context.get("nifty_change")
    stats["bank_nifty_change"] = market_context.get("bank_nifty_change")
    stats["timeframe"] = timeframe

    # 1. Download benchmark first to ensure the regime filter is available
    benchmark_period = "2y" if timeframe == "1d" else "60d"
    try:
        nifty = yf.download("^NSEI", period=benchmark_period, interval=timeframe, progress=False)
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty_close = nifty["Close"].dropna()
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").error(f"Benchmark download error: {exc}")
        return pd.DataFrame(), stats

    # 1.5 Prefetch Metadata (Background Batch Task)
    if progress_callback: progress_callback(0.05)
    prefetch_metadata(tickers)
    if progress_callback: progress_callback(0.10)

    # 2. Download ticker data in chunks of 50 to improve stability for large universes (Total Market)
    download_weight = 0.4
    chunk_size = 50
    data_frames = []
    num_chunks = (len(tickers) + chunk_size - 1) // chunk_size

    for i, start_idx in enumerate(range(0, len(tickers), chunk_size)):
        chunk = tickers[start_idx : start_idx + chunk_size]
        try:
            # RS rating and breakout checks need enough history; choose daily 2y or intraday 60d.
            chunk_period = "2y" if timeframe == "1d" else "60d"
            chunk_data = yf.download(chunk, period=chunk_period, interval=timeframe, progress=False, timeout=45)
            if not chunk_data.empty:
                data_frames.append(chunk_data)

            if progress_callback:
                progress_callback(0.10 + ((i + 1) / num_chunks * download_weight))
        except Exception as exc:
            logging.getLogger("AlphaScanner.Engine").warning(f"Chunk starting with {chunk[0]} failed: {exc}")
            if progress_callback:
                progress_callback((i + 1) / num_chunks * download_weight)

    if not data_frames:
        logging.getLogger("AlphaScanner.Engine").error("No ticker data could be downloaded.")
        return pd.DataFrame(), stats

    try:
        data = pd.concat(data_frames, axis=1, sort=True)
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").error(f"Data concatenation failed: {exc}")
        return pd.DataFrame(), stats

    if data.empty:
        return pd.DataFrame(), stats

    # 2.5 Market Breadth Calculation (Pro Feature)
    # Successful traders only trade breakouts when Breadth > 50%
    try:
        all_close = data['Close']
        all_sma50 = all_close.rolling(50).mean()
        breadth_50 = (all_close.iloc[-1] > all_sma50.iloc[-1]).mean() * 100
        stats["market_breadth_50"] = round(breadth_50, 1)
    except: pass

    avail = (
        data.columns.get_level_values(1).unique().tolist()
        if isinstance(data.columns, pd.MultiIndex) else tickers
    )

    # Identify Trending Sectors (Sectors outperforming the benchmark)
    trending_sectors = set()
    sector_sentiment_map = {}
    if sector_map and not data.empty and len(nifty_close) > 1:
        try:
            ticker_returns = (data['Close'].iloc[-1] / data['Close'].iloc[-2] - 1) * 100
            nifty_ret = (nifty_close.iloc[-1] / nifty_close.iloc[-2] - 1) * 100

            sector_perf = {}
            for t, ret in ticker_returns.items():
                sect = sector_map.get(t)
                if sect and not pd.isna(ret):
                    sector_perf.setdefault(sect, []).append(ret)

            for s, rets in sector_perf.items():
                avg_ret = np.mean(rets)
                # 1. Performance Component (0-5)
                perf_diff = avg_ret - nifty_ret
                perf_score = np.clip((perf_diff / 1.5) * 5, 0, 5) if perf_diff > 0 else 0

                # 2. News Sentiment Component (0-5)
                news_score = 2.5 # Neutral fallback
                if HAS_TEXTBLOB:
                    try:
                        search = yf.Search(f"{s} sector India news", news_count=5)
                        if search.news:
                            polarities = [TextBlob(a.get("title", "")).sentiment.polarity for a in search.news]
                            news_score = ( (sum(polarities) / len(polarities)) + 1 ) * 2.5
                    except Exception: pass

                sector_sentiment_map[s] = round(perf_score + news_score, 1)
                if avg_ret > max(0, nifty_ret):
                    trending_sectors.add(s)

        except Exception as e:
            logging.getLogger("AlphaScanner.Engine").warning(f"Sector momentum calculation failed: {e}")

    stats["trending_sectors"] = list(trending_sectors)
    stats["sector_sentiment"] = sector_sentiment_map

    stats_lock = Lock()
    hits = []

    # Use ThreadPoolExecutor for concurrent processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {
            executor.submit(
                _process_single_ticker,
                ticker, data, nifty_close, vol_thresh, rsi_min, rsi_max, dist_thresh,
                apply_market_cap_filter, min_mkt_cap_cr, max_mkt_cap_cr, scanner_type, universe, timeframe,
                sector_map, trending_sectors, sector_sentiment_map, market_context, stats, stats_lock
            ): ticker for ticker in avail
        }

        for i, future in enumerate(concurrent.futures.as_completed(future_to_ticker)):
            res = future.result()
            if res:
                hits.append(res)

            if progress_callback:
                # Final 50% of progress bar for signal processing (starting from 50%)
                progress_callback(0.50 + ((i + 1) / len(avail) * 0.50))

    df_out = pd.DataFrame(hits).sort_values("Signal_Strength", ascending=False) if hits else pd.DataFrame()

    return df_out, stats


def run_daily_cache_update():
    """Target function for a cron job to update scan results after market hours."""
    logging.getLogger("AlphaScanner.Engine").info("Starting automated post-market cache update...")
    from alphascanner_ui.data import get_sector_mapping

    # Common presets to cache
    for scan_type in ["Breakout", "Pre-Breakout"]:
        sector_map = get_sector_mapping("Nifty 500")
        rsi_min, rsi_max = (50, 85) if scan_type == "Breakout" else (35, 70)
        vol_thresh = 1.0 if scan_type == "Breakout" else 0.6
        dist_thresh = 1.5 if scan_type == "Breakout" else 5.0
        results, stats = run_scanner(
            universe="Nifty 500",
            vol_thresh=vol_thresh,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            dist_thresh=dist_thresh,
            scanner_type=scan_type,
            sector_map=sector_map
        )
        if not results.empty:
            save_results_to_db(results, stats)
    logging.getLogger("AlphaScanner.Engine").info("Daily cache update complete.")


def fetch_fii_dii_data(logger=None):
    """Fetches Daily FII/DII activity from NSE with robust session handling and caching."""
    if logger is None:
        logger = logging.getLogger("AlphaScanner.Engine")
    # 1. Try to get from cache (Expiry 4 hours)
    cached_data = get_system_cache("fii_dii_activity", expiry_hours=4)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass

    # 2. If no cache or expired, fetch from NSE
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/reports/fii-dii",
        "X-Requested-With": "XMLHttpRequest"
    }

    try:
        session = requests.Session()
        # Visit home page first to establish session cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=10)

        # Now fetch the actual data
        api_url = "https://www.nseindia.com/api/fiidiiTradeReact"
        response = session.get(api_url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data:
                # Transform NSE list to summary dict expected by the UI
                summary = {
                    "fii_buy": 0.0, "fii_sell": 0.0, "fii_net": 0.0,
                    "dii_buy": 0.0, "dii_sell": 0.0, "dii_net": 0.0,
                    "date": "N/A"
                }
                for item in data:
                    cat = item.get("category", "").upper()
                    def clean_val(v):
                        try: return float(str(v).replace(",", ""))
                        except: return 0.0
                    if "FII" in cat:
                        summary["fii_buy"] = clean_val(item.get("buyValue"))
                        summary["fii_sell"] = clean_val(item.get("sellValue"))
                        summary["fii_net"] = clean_val(item.get("netValue"))
                        summary["date"] = item.get("date", "N/A")
                    elif "DII" in cat:
                        summary["dii_buy"] = clean_val(item.get("buyValue"))
                        summary["dii_sell"] = clean_val(item.get("sellValue"))
                        summary["dii_net"] = clean_val(item.get("netValue"))

                # Save to cache
                set_system_cache("fii_dii_activity", json.dumps(summary))
                return summary
    except Exception as e:
        logger.error(f"FII/DII fetch failed: {e}")

    # 3. Fallback to older cache if fetch failed (up to 1 week old)
    stale_data = get_system_cache("fii_dii_activity", expiry_hours=168)
    if stale_data:
        return json.loads(stale_data)

    return {
        "fii_buy": 0.0, "fii_sell": 0.0, "fii_net": 0.0,
        "dii_buy": 0.0, "dii_sell": 0.0, "dii_net": 0.0,
        "date": "N/A"
    }

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_system_cache(key: str, expiry_hours: int = 12) -> Optional[str]:
    """Fetch a value from the generic system cache if not expired."""
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=expiry_hours)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = _connect_db()
        cur = conn.cursor()
        cur.execute("SELECT value FROM system_cache WHERE key = ? AND updated_at > ?", (key, cutoff))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def set_system_cache(key: str, value: str):
    """Insert or update a value in the generic system cache."""
    init_db()
    try:
        conn = _connect_db()
        conn.execute(
            "INSERT OR REPLACE INTO system_cache (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def init_db():
    conn = _connect_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
            stats        TEXT,
            results_json TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticker_metadata (
            ticker        TEXT PRIMARY KEY,
            market_cap_cr REAL,
            roe           REAL,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_cache (
            key          TEXT PRIMARY KEY,
            value        TEXT,
            updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_metadata_cache(ticker: str, expiry_hours: int = 24) -> Tuple[Optional[float], Optional[float]]:
    """Fetch fundamental data from local DB if it hasn't expired."""
    init_db()
    cutoff = (datetime.now() - timedelta(hours=expiry_hours)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = _connect_db()
        cur = conn.cursor()
        cur.execute("SELECT market_cap_cr, roe FROM ticker_metadata WHERE ticker = ? AND updated_at > ?", (ticker, cutoff))
        row = cur.fetchone()
        conn.close()
        return row if row else (None, None)
    except Exception:
        return None, None


def update_metadata_cache(ticker: str, market_cap_cr: float, roe: float):
    """Insert or update fundamental metadata in the local cache."""
    try:
        conn = _connect_db()
        conn.execute(
            "INSERT OR REPLACE INTO ticker_metadata (ticker, market_cap_cr, roe, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (ticker, market_cap_cr, roe)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def clear_metadata_cache():
    """Delete all entries from the ticker_metadata table."""
    init_db()
    try:
        conn = _connect_db()
        conn.execute("DELETE FROM ticker_metadata")
        conn.commit()
        conn.close()
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").error(f"Metadata cache clear error: {exc}")


def get_cached_results(hours: int = 12, universe: Optional[str] = None, scanner_type: Optional[str] = None, timeframe: Optional[str] = None):
    init_db()
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = _connect_db()
        cur  = conn.cursor()
        cur.execute(
            "SELECT stats, results_json, timestamp FROM scans "
            "WHERE timestamp > ? ORDER BY timestamp DESC",
            (cutoff,),
        )
        rows = cur.fetchall()
        conn.close()
        for row in rows:
            stats = json.loads(row[0])
            if universe and stats.get("universe") not in (universe, None):
                continue
            if scanner_type and stats.get("scanner_type") != scanner_type:
                continue
            if timeframe and stats.get("timeframe") != timeframe:
                continue
            return pd.read_json(io.StringIO(row[1])), stats, row[2]
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").error(f"Cache read error: {exc}")
    return None, None, None


def save_results_to_db(df: pd.DataFrame, stats: dict):
    init_db()
    try:
        conn = _connect_db()
        conn.execute(
            "INSERT INTO scans (stats, results_json) VALUES (?, ?)",
            (json.dumps(stats), df.to_json()),
        )
        conn.commit()
        conn.close()
    except Exception as exc: # Catch all exceptions during DB write
        logging.getLogger("AlphaScanner.Engine").error(f"DB write error: {exc}")


# ---------------------------------------------------------------------------
# Back-test
# ---------------------------------------------------------------------------

def run_backtest(
    start_date=None, end_date=None,
    lookback_days: int = 30, trade_window: int = 10,
    vol_thresh: float = 1.5, rsi_min: float = 60,
    rsi_max: float = 78, dist_thresh: float = 1.5,
):
    tickers = get_nifty_500()
    # Fetch Nifty data first to act as a regime filter
    try:
        data = yf.download(tickers, period="2y", interval="1d", progress=False, timeout=90)
        nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)

        nifty["SMA50"] = nifty["Close"].rolling(50).mean()
        nifty_close = nifty["Close"]
        nifty_sma50 = nifty["SMA50"]
    except Exception as exc:
        return pd.DataFrame(), f"Download error: {exc}"

    if data is None or data.empty:
        return pd.DataFrame(), "No data received."

    avail = (
        data.columns.get_level_values(1).unique().tolist()
        if isinstance(data.columns, pd.MultiIndex) else tickers
    )

    results = []

    for ticker in avail:
        try:
            df = _extract_ticker(data, ticker)
            df = df.dropna(subset=["Close", "High", "Low", "Open", "Volume"])
            if len(df) < 252:
                continue

            close = df["Close"]; high = df["High"]; low = df["Low"]; vol = df["Volume"]
            df["SMA200"]     = close.rolling(200).mean()
            df["SMA50"]      = close.rolling(50).mean()
            df["EMA20"]      = close.ewm(span=20, adjust=False).mean()
            df["AvgVol"]     = vol.rolling(30).mean().shift(1)
            df["RSI"]        = calculate_rsi(close)
            df["ATR"]        = calculate_atr(high, low, close)
            df["ADX"]        = calculate_adx(high, low, close)

            # New Indicators for 11-Filter System
            df["MACD"], df["MACD_Signal"], _ = calculate_macd(close)
            df["Stoch_K"], _ = calculate_stochastic_rsi(df["RSI"].fillna(50))
            df["EMA20_Slope"] = df["EMA20"].diff(3) > 0
            df["SMA50_Slope"] = df["SMA50"].diff(3) > 0

            df["BB_Upper"], df["BB_Mid"], df["BB_Lower"] = calculate_bollinger_bands(close)
            bb_rng = (df["BB_Upper"] - df["BB_Lower"]).replace(0, np.nan)
            df["BB_Position"] = (close - df["BB_Lower"]) / bb_rng
            df["VWAP"]       = calculate_vwap(high, low, close, vol)

            if start_date and end_date:
                mask = (df.index.date >= start_date) & (df.index.date <= end_date)
                idx_list = list(np.where(mask)[0])
            else:
                total = len(df)
                idx_list = list(range(max(0, total - trade_window - lookback_days),
                                      max(0, total - trade_window)))

            for i in idx_list:
                if i < 252:
                    continue
                row  = df.iloc[i]
                ltp  = float(row["Close"])
                atr  = float(row["ATR"]) if not pd.isna(row["ATR"]) else ltp * 0.015
                if atr <= 0:
                    continue

                # 11-Filter Component Calculations
                ph20 = float(df["High"].iloc[i-21:i].max())
                h52  = float(df["High"].iloc[i-252:i].max())
                actual_breakout = ltp > ph20
                near_20d = ph20 * (1 - dist_thresh / 100) <= ltp <= ph20 * 1.005
                near_52w = h52 * (1 - dist_thresh / 100) <= ltp <= h52 * 1.005
                actual_breakout_condition_met = actual_breakout or near_20d or near_52w

                vol_ratio = float(row["Volume"]) / max(float(row["AvgVol"]), 1)
                trend_stack_ok = ltp > row["EMA20"] > row["SMA50"] > row["SMA200"]

                range_day = float(row["High"] - row["Low"])
                relative_close = (ltp - float(row["Low"])) / range_day if range_day > 0 else 0

                bb_upper_zone = ltp >= (row["BB_Mid"] + (row["BB_Upper"] - row["BB_Mid"]) * 0.5)
                bb_breakout = ltp > row["BB_Upper"]
                bb_bull = bb_upper_zone or bb_breakout
                macd_bull = row["MACD"] > row["MACD_Signal"]
                above_vwap = ltp > row["VWAP"]
                stoch_neutral = 20 <= row["Stoch_K"] <= 80
                ma_slope_bull = row["EMA20_Slope"] and row["SMA50_Slope"]

                # Pattern Detections
                window_df = df.iloc[max(0, i-50):i+1]
                is_tight = detect_vcp_tightness(window_df["Close"])
                is_dry = detect_volume_dryup(window_df["Volume"])
                is_inside_bar = detect_inside_bar(window_df)
                is_nr7 = detect_nr7(window_df)

                # RS Approximation for historical accuracy
                stock_slice = df["Close"].iloc[max(0, i-252):i+1]
                nifty_slice = nifty_close.loc[stock_slice.index]
                rs_rating = calculate_relative_strength(stock_slice, nifty_slice)

                # Candlestick Intelligence
                candle = detect_candlestick_pattern(df.iloc[:i+1])

                # Standardized 11-Filter Confluence Scoring (Matches run_scanner)
                score = 0.0
                score += 1.5 if trend_stack_ok else 0.0
                score += 1.0 if vol_ratio >= 1.5 else 0.5
                score += 1.0 if (rsi_min <= row["RSI"] <= rsi_max) else 0.0
                score += 1.5 if relative_close >= 0.7 else 0.0
                score += 1.0 if row["ADX"] > 20 else 0.0
                score += 1.0 if actual_breakout_condition_met else 0.0
                score += 1.0 if macd_bull else 0.0
                score += 1.0 if bb_bull else 0.0
                score += 0.5 if above_vwap else 0.0
                score += 0.5 if stoch_neutral else 0.0
                score += 1.0 if ma_slope_bull else 0.0

                # Pattern Bonuses
                if is_tight and is_dry: score += 1.5
                if is_inside_bar and is_nr7: score += 2.0
                if rs_rating >= 90: score += 1.0

                strength = min(10.0, max(0.0, round(score, 1)))

                current_date = df.index[i]
                market_close = nifty_close.get(current_date)
                market_sma50 = nifty_sma50.get(current_date)
                market_is_bullish = (
                    market_close is not None
                    and market_sma50 is not None
                    and not pd.isna(market_close)
                    and not pd.isna(market_sma50)
                    and float(market_close) > float(market_sma50)
                )

                # Strategy Filters + Broad Market Regime Filter
                checks = [
                    market_is_bullish,
                    trend_stack_ok,
                    actual_breakout_condition_met,
                    strength >= 6.0, # Minimum conviction threshold for a backtested entry
                    candle != "Neutral" or is_inside_bar
                ]

                if not all(checks):
                    continue

                risk = 1.5 * atr
                sl = ltp - risk
                tp = ltp + 3.0 * atr
                breakeven_trigger = ltp + 1.5 * atr

                outcome = "Pending"
                exit_date = None
                exit_price = np.nan
                pnl_r = np.nan
                holding_days = 0
                hit_breakeven = False

                end_j = min(i + trade_window, len(df) - 1)
                for j in range(i + 1, end_j + 1):
                    fr = df.iloc[j]
                    holding_days = j - i

                    if not hit_breakeven and float(fr["High"]) >= breakeven_trigger:
                        hit_breakeven = True

                    current_sl = ltp if hit_breakeven else sl

                    if float(fr["Low"]) <= current_sl:
                        outcome = "Loss"
                        exit_date = df.index[j].date()
                        exit_price = current_sl
                        pnl_r = 0.0 if hit_breakeven else -1.0
                        break
                    if float(fr["High"]) >= tp:
                        outcome = "Win"
                        exit_date = df.index[j].date()
                        exit_price = tp
                        pnl_r = 2.0
                        break

                if outcome == "Pending" and end_j >= i + trade_window:
                    exit_row = df.iloc[end_j]
                    exit_date = df.index[end_j].date()
                    exit_price = float(exit_row["Close"])
                    pnl_r = (exit_price - ltp) / risk if risk > 0 else 0.0
                    pnl_r = float(np.clip(pnl_r, -1.0, 2.0))
                    holding_days = end_j - i
                    outcome = "Expired"

                results.append({
                    "Date": df.index[i].date(),
                    "Ticker": ticker,
                    "Outcome": outcome,
                    "Entry": round(ltp, 2),
                    "Stop": round(sl, 2),
                    "Target": round(tp, 2),
                    "Exit_Date": exit_date,
                    "Strength": strength,
                    "Candle": candle,
                    "Exit": round(exit_price, 2) if not pd.isna(exit_price) else np.nan,
                    "PnL_R": round(pnl_r, 3) if not pd.isna(pnl_r) else np.nan,
                    "Holding_Days": holding_days,
                })

        except Exception:
            continue

    return (pd.DataFrame(results) if results else pd.DataFrame()), None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    print("Running AlphaScanner...")
    results, stats = run_scanner()
    print(f"Scan Summary: {stats}")
    print(results.to_string(index=False) if not results.empty else "No candidates found.")


if __name__ == "__main__":
    main()
