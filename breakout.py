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
import concurrent.futures
from datetime import datetime, timedelta
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
    "scanned": 0, "volume_fail": 0, "trend_fail": 0,
    "breakout_fail": 0, "momentum_fail": 0, "adx_fail": 0,
    "macd_fail": 0, "bb_fail": 0, "rs_fail": 0, "fakeout_trap": 0,
    "trending_sectors": [], "sector_sentiment": {},
    "universe": None, "universe_size": 0,
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

    logger = logging.getLogger("AlphaScanner.Engine")
    for url in urls:
        try:
            df = _fetch_nse_csv(url)
            symbols = _extract_symbols_from_index_csv(df)
            if symbols:
                logger.info("Fetched %s symbols for %s from %s", len(symbols), label, url)
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


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def is_market_open() -> bool:
    """Checks if the NSE market is currently open (9:15 AM - 3:30 PM IST, Mon-Fri)."""
    # IST is UTC + 5:30
    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)

    # Weekends (Saturday=5, Sunday=6)
    if now_ist.weekday() >= 5:
        return False

    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= now_ist <= market_close


def get_last_market_close_utc() -> datetime:
    """Returns the UTC datetime of the most recent NSE market close."""
    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    
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
    return 100 - (100 / (1 + gain / loss.replace(0, np.nan)))


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
    return float(volume.iloc[-1]) >= (avg_vol_short * threshold)

def detect_candlestick_pattern(df: pd.DataFrame) -> str:
    """Detects simple candlestick patterns for high-conviction entries."""
    if len(df) < 2: return "Neutral"
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    body = last['Close'] - last['Open']
    abs_body = abs(body)
    range_ = max(last['High'] - last['Low'], 1e-9)
    upper_wick = last['High'] - max(last['Open'], last['Close'])
    lower_wick = min(last['Open'], last['Close']) - last['Low']
    
    # Hammer / Bullish Pin Bar
    if lower_wick > 2 * abs_body and upper_wick < 0.1 * range_:
        return "Bullish Hammer"
    # Bullish Engulfing
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
    to_fetch = [t for t in tickers if get_metadata_cache(t)[0] is None]
    
    if not to_fetch:
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
    sector_map: Optional[dict],
    trending_sectors: set,
    sector_sentiment_map: dict,
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

        # Indicators
        sma_200 = close.rolling(200).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1]
        ema_20 = close.ewm(span=20, adjust=False).mean().iloc[-1]

        avg_vol = vol.rolling(30).mean().iloc[-2]
        rsi = calculate_rsi(close).iloc[-1]
        adx_series = calculate_adx(high, low, close)
        adx = adx_series.iloc[-1]
        adx_prev = adx_series.iloc[-2]
        macd, macd_sig, macd_hist = calculate_macd(close)
        upper_bb, mid_bb, lower_bb = calculate_bollinger_bands(close)
        vwap = calculate_vwap(high, low, close, vol).iloc[-1]

        ltp = float(close.iloc[-1])
        ticker_sector = sector_map.get(ticker, "N/A") if sector_map else "N/A"
        sector_score = sector_sentiment_map.get(ticker_sector, 5.0)
        is_tight = detect_vcp_tightness(close)
        is_inside_bar = detect_inside_bar(df)
        is_nr7 = detect_nr7(df)
        base_weeks = calculate_base_weeks(df)
        consol_days = calculate_consolidation_days(df)
        is_dry = detect_volume_dryup(vol)

        # GRANULAR SETUP SCORE (0-10) for Pre-Breakout Ranking
        recent_std = close.tail(10).std()
        hist_std = close.tail(50).std()
        tightness_ratio = (recent_std / hist_std) if hist_std > 0 else 1.0
        # 1. RSI Accumulation Score: Centered at 52.5 (Max 5 pts)
        rsi_acc_score = max(0, 5 - abs(rsi - 52.5) / 2.5) if 40 <= rsi <= 65 else 0
        # 2. Tightness Score: Max points if ratio <= 0.5 (Max 5 pts)
        t_acc_score = max(0, min(5.0, (0.75 - tightness_ratio) / 0.25 * 5)) if tightness_ratio < 0.75 else 0
        setup_score = round(min(10.0, rsi_acc_score + t_acc_score), 1)

        # Volume Surge is validated only if the stock belongs to a trending/outperforming sector
        is_surge = detect_volume_surge(vol)
        if sector_map and ticker_sector != "N/A":
            is_surge = is_surge and (ticker_sector in trending_sectors)

        # Volume filter
        vol_ratio = float(vol.iloc[-1]) / max(avg_vol, 1)
        min_vol_ratio = float(vol_thresh)

        # Relaxed Trend filter: Just needs short-term alignment
        # Pre-Breakout allows price to be resting slightly below EMA20
        trend_ok = (ltp > ema_20 * 0.99) and (ema_20 > sma_50) if scanner_type == "Pre-Breakout" else (ltp > ema_20 and ema_20 > sma_50)
        if not trend_ok:
            with stats_lock: stats["trend_fail"] += 1
            return None

        # RSI filter
        if not (rsi_min <= rsi <= rsi_max):
            with stats_lock: stats["momentum_fail"] += 1
            return None

        # RS filter
        rs_rating = calculate_relative_strength(close_aligned, nifty_aligned)
        rs_floor = 50 if "Total Market" in universe else 60
        if scanner_type == "Pre-Breakout":
            rs_floor -= 10 # Accumulating stocks have lower immediate RS
            
        if rs_rating < rs_floor and not (rs_rating == 0 and rsi > 70):
            with stats_lock: stats["rs_fail"] += 1
            return None

        rs_bonus = 3 if rs_rating >= 95 else (2 if rs_rating >= 90 else 0)

        # ADX rising condition
        if not (adx > (12 if scanner_type == "Pre-Breakout" else 18)): # Lowered floor for Pre-Breakout
            with stats_lock: stats["adx_fail"] += 1
            return None
        
        # Breakout logic
        prev_h20 = float(high.iloc[-21:-1].max())
        prev_h52 = float(high.iloc[-252:-1].max())
        
        # ANTICIPATORY LOGIC: Is it about to break?
        # Price is within 1.5% of 20-day high OR 52-week high
        near_20d = prev_h20 * (1 - dist_thresh / 100) <= ltp <= prev_h20 * 1.005
        near_52w = prev_h52 * (1 - dist_thresh / 100) <= ltp <= prev_h52 * 1.005
        
        # Initialize flags to avoid UnboundLocalError
        is_breaking_out = False
        is_consolidating_near_20d = False
        is_consolidating_near_52w = False
        actual_breakout_condition_met = False

        if scanner_type == "Breakout":
            is_breaking_out = ltp > prev_h20 * 1.005 or ltp > prev_h52 * 1.005
            actual_breakout_condition_met = near_20d or near_52w or is_breaking_out
        else: # Pre-Breakout
            # Pre-Breakout: Price within proximity threshold but hasn't surged past resistance yet
            is_consolidating_near_20d = ltp >= prev_h20 * (1 - dist_thresh / 100) and ltp < prev_h20 * 1.005
            is_consolidating_near_52w = ltp >= prev_h52 * (1 - dist_thresh / 100) and ltp < prev_h52 * 1.005
            is_breaking_out = ltp > prev_h20 * 1.005 # Still tracked for labeling
            actual_breakout_condition_met = is_consolidating_near_20d or is_consolidating_near_52w

        # Fakeout detection: price breaks resistance but volume is below threshold
        is_fakeout = is_breaking_out and vol_ratio < min_vol_ratio
        if vol_ratio < min_vol_ratio and not (is_tight and is_dry or is_breaking_out):
            with stats_lock: stats["volume_fail"] += 1
            return None
        
        if not actual_breakout_condition_met:
            with stats_lock: stats["breakout_fail"] += 1
            return None

        # Candle confirmation
        body = abs(close.iloc[-1] - df["Open"].iloc[-1])
        range_ = high.iloc[-1] - low.iloc[-1]
        if range_ == 0 or (body / range_) < 0.3:
            return None

        # Anti-Chase Filter: Increased threshold for small caps
        daily_pcnt = (ltp - df["Open"].iloc[-1]) / df["Open"].iloc[-1] * 100
        if daily_pcnt > 8.0:
            return None

        candle_sentiment = detect_candlestick_pattern(df)
        
        # Trend Intensity based on MA Slopes and ADX
        ema_20_prev = close.ewm(span=20, adjust=False).mean().iloc[-5]
        trend_slope = (ema_20 - ema_20_prev) / max(ema_20_prev, 1e-9) * 100
        trend_intensity = "Strong" if (adx > 25 and trend_slope > 0.5) else ("Moderate" if adx > 20 else "Weak")

        # MACD confirmation
        macd_bull = macd.iloc[-1] > macd_sig.iloc[-1] and macd_hist.iloc[-1] > 0

        # BB & VWAP confirmation
        bb_upper_zone = ltp >= (mid_bb.iloc[-1] + (upper_bb.iloc[-1] - mid_bb.iloc[-1]) * 0.5)
        bb_breakout = ltp > upper_bb.iloc[-1]
        above_vwap = ltp > vwap
        bb_bull = bb_upper_zone or bb_breakout

        # Additional confirmations used in scoring and UI.
        ma_slope_bull = ema_20 > close.ewm(span=20, adjust=False).mean().iloc[-6]
        bull_div, bear_div = detect_divergence(close, calculate_rsi(close))
        atr = calculate_atr(high, low, close).iloc[-1]
        atr = float(atr) if not pd.isna(atr) and atr > 0 else ltp * 0.015
        support_breakout, near_support, resistance, support = detect_support_resistance(df)

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
        if is_fakeout:
            patterns.append("Fakeout-Trap")
            with stats_lock: stats["fakeout_trap"] += 1

        # Enhanced Weighted Signal Strength Scoring (0-10)
        if scanner_type == "Pre-Breakout":
            strength = (1.5 + (setup_score * 0.35) if is_dry else 1.0) # Weighted by setup quality and supply dry-up
            strength += (2.0 if is_consolidating_near_20d else 0) + (1.5 if is_consolidating_near_52w else 0)
            strength += (0.5 if macd_bull else 0) + (0.5 if above_vwap else 0) + (0.5 if bb_bull else 0)
            strength += (0.5 if ma_slope_bull else 0)
            strength += (1.0 if is_surge else 0) # Surge is still good for early accumulation
            strength += (setup_score / 5.0) # Bonus for high-quality technical setup
            if is_inside_bar and is_tight:
                strength += 1.5 # Inside bar during tight consolidation is high conviction
            if is_inside_bar and is_nr7:
                strength += 2.0 # NR7 + Inside Bar "SuperCoil"
        else: # Breakout scanner
            strength = (3.0 if (is_tight and is_dry) else 1.0) 
            strength += (2.5 if near_20d else 0) + (2.0 if near_52w else 0)
            strength += (1 if macd_bull else 0) + (1 if above_vwap else 0) + (1 if bb_bull else 0)
            strength += (1 if ma_slope_bull else 0)
            strength += (2.0 if is_surge else 0)

            if is_inside_bar and is_tight:
                strength += 2.0 # Volatility contraction + Inside bar is a coil
            if is_inside_bar and is_nr7:
                strength += 2.5 # Extremely high-conviction coil

        strength += max(0, (rs_rating - 70) / 5) # Gradual contribution from RS

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

        # TRIGGER LOGIC (OR): At least one major signal must be present
        if scanner_type == "Pre-Breakout":
            # For pre-breakout, we allow Tightness OR Dry-up OR proximity
            if not (is_tight or is_dry or is_consolidating_near_20d or is_consolidating_near_52w or len(patterns) > 0):
                with stats_lock: stats["breakout_fail"] += 1
                return None
        else: # Breakout scanner
            if not (is_breaking_out or near_52w or bb_breakout or len(patterns) > 0):
                with stats_lock: stats["breakout_fail"] += 1
                return None

        return {
            "Ticker": ticker,
            "Type": "Breakout",
            "LTP": round(ltp, 2),
            "ATR": round(atr, 2),
            "RSI": round(rsi, 1),
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
            "_Support1": round(float(support), 2),
            "_Support2": round(float(sma_200), 2),
            "_Resistance": round(float(resistance), 2),
            "Signal_Strength": strength,
            "Trend": trend_intensity,
            "Candle": "Consolidating" if daily_pcnt < 1.5 else candle_sentiment,
            "Action": "AVOID: Fakeout" if is_fakeout else (
                "VCP Setup" if (scanner_type == "Pre-Breakout" and is_tight and is_dry) else
                ("Near Breakout" if (scanner_type == "Pre-Breakout" and (is_consolidating_near_20d or is_consolidating_near_52w)) else
                 ("ID/NR7 SuperCoil" if (is_inside_bar and is_nr7) else
                  ("Inside Bar Coil" if (is_inside_bar and is_tight) else
                   ("Ready to Pop" if (strength >= 7.5 and is_tight) else "Watching"))))
            ),
            "Pattern": ", ".join(patterns) if patterns else ("20D Breakout" if is_breaking_out else ("Near 52W" if near_52w else "Vol Breakout")),
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

    # 1. Download benchmark first to ensure the regime filter is available
    try:
        nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)
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
            # RS rating and 52-week checks need at least 252 aligned trading days; use 2y.
            chunk_data = yf.download(chunk, period="2y", interval="1d", progress=False, timeout=45)
            if not chunk_data.empty:
                data_frames.append(chunk_data)
            
            if progress_callback:
                progress_callback((i + 1) / num_chunks * download_weight)
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
                ticker, data, nifty_close, vol_thresh, rsi_min, rsi_max, dist_thresh, # Pass scanner_type
                apply_market_cap_filter, min_mkt_cap_cr, max_mkt_cap_cr, scanner_type, universe, sector_map, trending_sectors, sector_sentiment_map, stats, stats_lock
            ): ticker for ticker in avail
        }
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_ticker)):
            res = future.result()
            if res:
                hits.append(res)
            
            if progress_callback:
                # Final 60% of progress bar for signal processing
                progress_callback(download_weight + ((i + 1) / len(avail) * (1 - download_weight)))

    df_out = pd.DataFrame(hits).sort_values("Signal_Strength", ascending=False) if hits else pd.DataFrame()

    return df_out, stats


def run_daily_cache_update():
    """Target function for a cron job to update scan results after market hours."""
    logging.getLogger("AlphaScanner.Engine").info("Starting automated post-market cache update...")
    from alphascanner_ui.data import get_sector_mapping

    # Common presets to cache
    for scan_type in ["Breakout", "Pre-Breakout"]:
        sector_map = get_sector_mapping("Nifty 500")
        results, stats = run_scanner(
            universe="Nifty 500",
            vol_thresh=1.5,
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
    cutoff = (datetime.utcnow() - timedelta(hours=expiry_hours)).strftime("%Y-%m-%d %H:%M:%S")
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


def get_cached_results(hours: int = 12, universe: Optional[str] = None):
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
            df["MACD"], df["MACD_Signal"], _ = calculate_macd(close)
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

                ph20 = float(df["High"].iloc[i-21:i].max())
                h52  = float(df["High"].iloc[i-252:i].max())

                # New Weighted Signal Calculation for Backtest
                actual_breakout = ltp > ph20
                near_52w = ltp >= h52 * (1 - dist_thresh / 100)
                
                # BB logic matching scanner
                bb_upper_zone = ltp >= (row["BB_Mid"] + (row["BB_Upper"] - row["BB_Mid"]) * 0.5)
                bb_breakout = ltp > row["BB_Upper"]
                bb_bull = bb_upper_zone or bb_breakout
                
                macd_bull = row["MACD"] > row["MACD_Signal"]
                above_vwap = ltp > row["VWAP"]
                
                # Candlestick Intelligence
                candle = detect_candlestick_pattern(df.iloc[:i+1])
                
                # Weighted Score (consistent with run_scanner)
                strength = (3 if actual_breakout else 0) + (1.5 if near_52w else 0)
                strength += (1 if macd_bull else 0) + (1 if above_vwap else 0) + (1 if bb_bull else 0)
                # RS Contribution (approximate rating for backtest)
                strength += 1.5 if ltp > row["SMA200"] else 0
                strength = min(10.0, round(strength, 1))

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
                    market_is_bullish, # Market must be bullish
                    ltp > row["EMA20"] > row["SMA50"] > row["SMA200"],
                    row["Volume"] > vol_thresh * row["AvgVol"],
                    rsi_min <= row["RSI"] <= rsi_max,
                    not pd.isna(row["ADX"]) and row["ADX"] >= 20,
                    ltp > ph20, # Must be an actual breakout above 20-day resistance
                    strength >= 5.0, # Minimum conviction threshold for backtest
                    candle != "Neutral"
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
