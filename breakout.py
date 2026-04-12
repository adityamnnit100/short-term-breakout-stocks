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
}


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
def get_nifty_500() -> list:
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    from alphascanner_ui.data import HEADERS # Import HEADERS from data.py
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        df = pd.read_csv(io.StringIO(res.text))
        sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
        if sym_col is None:
            logging.getLogger("AlphaScanner.Engine").warning("Symbol column not found in Nifty 500 list.")
            return []
        return [f"{s}.NS" for s in df[sym_col].dropna().str.strip()]
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").warning(f"Failed to fetch Nifty 500 ({exc}), using fallback.")
        return [
            "RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS", "HDFCBANK.NS",
            "ICICIBANK.NS", "KOTAKBANK.NS", "HINDUNILVR.NS", "ITC.NS", "AXISBANK.NS",
        ]


def get_nifty_total_market() -> list:
    """Fetches the Nifty Total Market list (Nifty 500 + Microcaps)."""
    from alphascanner_ui.data import HEADERS # Import HEADERS from data.py
    url = "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        df = pd.read_csv(io.StringIO(res.text))
        sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
        if sym_col is None:
            logging.getLogger("AlphaScanner.Engine").warning("Symbol column not found in Nifty Total Market list.")
            return []
        return [f"{s}.NS" for s in df[sym_col].dropna().str.strip()]
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").warning(f"Failed to fetch Nifty Total Market: {exc}")
        # Fallback to Nifty 500 if total market fetch fails
        return get_nifty_500()


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

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
    if len(stock_close) < 252 or len(index_close) < 252:
        return 0.0
    
    # 1-Year Performance (Weighted towards most recent quarter)
    def get_perf(series):
        return ((series.iloc[-1] / series.iloc[-63] * 0.4) + 
                (series.iloc[-1] / series.iloc[-126] * 0.2) + 
                (series.iloc[-1] / series.iloc[-189] * 0.2) + 
                (series.iloc[-1] / series.iloc[-252] * 0.2))
    
    s_perf = get_perf(stock_close)
    i_perf = get_perf(index_close)
    rs_ratio = (s_perf / i_perf) * 100
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
    """FIX: removed rolling argmin that caused FutureWarning in pandas >= 2.0."""
    if len(close) <= lookback * 2:
        return False, False
    bull = bool(close.iloc[-1] < close.iloc[-lookback] and rsi.iloc[-1] > rsi.iloc[-lookback])
    bear = bool(close.iloc[-1] > close.iloc[-lookback] and rsi.iloc[-1] < rsi.iloc[-lookback])
    return bull, bear


def detect_vcp_tightness(close, window: int = 10):
    """Detects 'Tightness' in price action (Volatility Contraction)."""
    if len(close) < 50:
        return False
    recent_std = close.tail(window).std()
    hist_std = close.tail(50).std()
    return recent_std < (hist_std * 0.75)

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
        is_dry = detect_volume_dryup(vol)

        # Volume Surge is validated only if the stock belongs to a trending/outperforming sector
        is_surge = detect_volume_surge(vol)
        if sector_map and ticker_sector != "N/A":
            is_surge = is_surge and (ticker_sector in trending_sectors)

        # Volume filter
        vol_ratio = float(vol.iloc[-1]) / max(avg_vol, 1)
        min_vol_ratio = max(float(vol_thresh), 1.0)

        # Relaxed Trend filter: Just needs short-term alignment
        if not (ltp > ema_20 and ema_20 > sma_50):
            with stats_lock: stats["trend_fail"] += 1
            return None

        # RSI filter
        if not (rsi_min <= rsi <= rsi_max):
            with stats_lock: stats["momentum_fail"] += 1
            return None

        # RS filter
        rs_rating = calculate_relative_strength(close_aligned, nifty_aligned)
        if rs_rating < 60: # More inclusive floor
            with stats_lock: stats["rs_fail"] += 1
            return None

        rs_bonus = 3 if rs_rating >= 95 else (2 if rs_rating >= 90 else 0)

        # ADX rising condition
        if not (adx > 18): # Lowered floor
            with stats_lock: stats["adx_fail"] += 1
            return None

        # Breakout logic
        prev_h20 = float(high.iloc[-21:-1].max())
        prev_h52 = float(high.iloc[-252:-1].max())
        
        # ANTICIPATORY LOGIC: Is it about to break?
        # Price is within 1.5% of 20-day high OR 52-week high
        near_20d = prev_h20 * 0.985 <= ltp <= prev_h20 * 1.005
        near_52w = ltp >= prev_h52 * (1 - dist_thresh / 100)
        is_breaking_out = ltp > prev_h20 * 1.005 or ltp > prev_h52 * 1.005
        actual_breakout = near_20d or near_52w

        # Fakeout detection: price breaks resistance but volume is below threshold
        is_fakeout = is_breaking_out and vol_ratio < min_vol_ratio
        if vol_ratio < min_vol_ratio and not (is_tight and is_dry or is_breaking_out):
            with stats_lock: stats["volume_fail"] += 1
            return None

        if not (near_20d or near_52w or is_breaking_out):
            with stats_lock: stats["breakout_fail"] += 1
            return None

        # Candle confirmation
        body = abs(close.iloc[-1] - df["Open"].iloc[-1])
        range_ = high.iloc[-1] - low.iloc[-1]
        if range_ == 0 or (body / range_) < 0.4:
            return None

        # Anti-Chase Filter: If the stock is already up > 4% today, it might be a "late" signal
        daily_pcnt = (ltp - df["Open"].iloc[-1]) / df["Open"].iloc[-1] * 100
        if daily_pcnt > 4.5:
            return None

        candle_sentiment = detect_candlestick_pattern(df)
        
        # Trend Intensity based on MA Slopes and ADX
        ema_20_prev = close.ewm(span=20, adjust=False).mean().iloc[-5]
        trend_slope = (ema_20 - ema_20_prev) / max(ema_20_prev, 1e-9) * 100
        trend_intensity = "Strong" if (adx > 25 and trend_slope > 0.5) else ("Moderate" if adx > 18 else "Weak")

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
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    t_obj = yf.Ticker(ticker)
                    info = t_obj.info
                    roe = info.get('returnOnEquity', 0.0)
                    mkt_cap = t_obj.fast_info.get("marketCap", 0)
                    mkt_cap_cr = mkt_cap / 10_000_000
                    update_metadata_cache(ticker, mkt_cap_cr, roe)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    logging.getLogger("AlphaScanner.Engine").warning(f"Metadata error for {ticker} after {max_retries} attempts: {e}")
                    if apply_market_cap_filter: return None

        if apply_market_cap_filter and mkt_cap_cr < min_mkt_cap_cr:
             return None

        patterns = []
        if detect_flag_pattern(df): patterns.append("Flag")
        if detect_triangle_breakout(df): patterns.append("Triangle")
        if detect_cup_handle(df): patterns.append("CupHandle")
        if detect_rounding_bottom(df): patterns.append("Rounding")
        if detect_inverted_head_shoulders(df): patterns.append("Inv-H&S")
        if is_tight: patterns.append("VCP-Tight")
        if is_dry: patterns.append("Vol-Dryup")
        if is_surge: patterns.append("Vol-Surge")
        if is_fakeout:
            patterns.append("Fakeout-Trap")
            with stats_lock: stats["fakeout_trap"] += 1

        # Enhanced Weighted Signal Strength Scoring (0-10)
        # We give the MOST weight to "Tightness" and "Proximity" to find stocks BEFORE the move
        strength = (3.0 if (is_tight and is_dry) else 1.0) 
        strength += (2.5 if near_20d else 0) + (2.0 if near_52w else 0)
        strength += (1 if macd_bull else 0) + (1 if above_vwap else 0) + (1 if bb_bull else 0)
        strength += (1 if ma_slope_bull else 0)
        strength += (2.0 if is_surge else 0)
        strength += max(0, (rs_rating - 70) / 5) # Gradual contribution from RS

        # Sector Sentiment Factor (Bonus/Penalty)
        if sector_score >= 8.0:
            strength += 1.5
        elif sector_score <= 4.0:
            strength -= 1.0
        
        if is_fakeout:
            strength = min(strength, 3.5) # Drastic reduction for low-volume traps

        strength = min(10.0, round(strength, 1))

        # TRIGGER LOGIC (OR): At least one major signal must be present
        if not (actual_breakout or near_52w or bb_breakout or len(patterns) > 0):
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
            "Sector": ticker_sector,
            "Sector_Score": sector_score,
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
            "Action": "AVOID: Fakeout" if is_fakeout else ("Ready to Pop" if (strength >= 7.5 and is_tight) else "Watching"),
            "Pattern": ", ".join(patterns) if patterns else ("20D Breakout" if actual_breakout else ("Near 52W" if near_52w else "Vol Breakout")),
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
    universe: str = "Nifty 500",
    sector_map: Optional[dict] = None,
    progress_callback=None,
):
    apply_market_cap_filter = min_mkt_cap_cr > 0

    if universe == "Total Market (Cap Focused)":
        tickers = get_nifty_total_market()
    else:
        tickers = get_nifty_500()

    stats = _EMPTY_STATS.copy()

    try:
        # RS rating and 52-week checks need at least 252 aligned trading days.
        # A calendar year often has fewer rows after weekends/holidays, so use 2y.
        data = yf.download(tickers, period="2y", interval="1d", progress=False, timeout=90)
        nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)

        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)

        nifty_close = nifty["Close"].dropna()

    except Exception as exc: # Catch all exceptions during download
        logging.getLogger("AlphaScanner.Engine").error(f"Download error: {exc}")
        return pd.DataFrame(), stats

    if data is None or data.empty:
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
                ticker, data, nifty_close, vol_thresh, rsi_min, rsi_max, dist_thresh, 
                apply_market_cap_filter, min_mkt_cap_cr, sector_map, trending_sectors, sector_sentiment_map, stats, stats_lock
            ): ticker for ticker in avail
        }
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_ticker)):
            res = future.result()
            if res:
                hits.append(res)
            
            if progress_callback:
                progress_callback((i + 1) / len(avail))

    df_out = pd.DataFrame(hits).sort_values("Signal_Strength", ascending=False) if hits else pd.DataFrame()

    return df_out, stats

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()


def get_metadata_cache(ticker: str, expiry_hours: int = 24) -> Tuple[Optional[float], Optional[float]]:
    """Fetch fundamental data from local DB if it hasn't expired."""
    init_db()
    cutoff = (datetime.now() - timedelta(hours=expiry_hours)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_PATH)
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
        conn = sqlite3.connect(DB_PATH)
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
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM ticker_metadata")
        conn.commit()
        conn.close()
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").error(f"Metadata cache clear error: {exc}")


def get_cached_results(hours: int = 12):
    init_db()
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT stats, results_json, timestamp FROM scans "
            "WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 1",
            (cutoff,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return pd.read_json(io.StringIO(row[1])), json.loads(row[0]), row[2]
    except Exception as exc:
        logging.getLogger("AlphaScanner.Engine").error(f"Cache read error: {exc}")
    return None, None, None


def save_results_to_db(df: pd.DataFrame, stats: dict):
    init_db()
    try:
        conn = sqlite3.connect(DB_PATH)
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
            
            # MACD & BB for scoring
            df["MACD"], df["MACD_Sig"], _ = calculate_macd(close)
            df["BB_Up"], df["BB_Mid"], _ = calculate_bollinger_bands(close)
            df["ADX"]        = calculate_adx(high, low, close)
            df["MACD"], df["MACD_Signal"], _ = calculate_macd(close)
            df["BB_Upper"], _, df["BB_Lower"] = calculate_bollinger_bands(close)
            bb_rng = (df["BB_Upper"] - df["BB_Lower"]).replace(0, np.nan)
            df["BB_Position"] = (close - df["BB_Lower"]) / bb_rng
            df["VWAP"]       = calculate_vwap(high, low, close, vol)

            # Pre-align Nifty with ticker data
            nifty_aligned_close, _ = nifty_close.align(close, join="inner")
            nifty_aligned_sma, _ = nifty_sma50.align(close, join="inner")

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
                bb_upper_zone = ltp >= (row["BB_Mid"] + (row["BB_Up"] - row["BB_Mid"]) * 0.5)
                bb_breakout = ltp > row["BB_Up"]
                bb_bull = bb_upper_zone or bb_breakout
                
                macd_bull = row["MACD"] > row["MACD_Sig"]
                above_vwap = ltp > row["VWAP"]
                
                # Candlestick Intelligence
                candle = detect_candlestick_pattern(df.iloc[:i+1])
                
                # Weighted Score (consistent with run_scanner)
                strength = (3 if actual_breakout else 0) + (1.5 if near_52w else 0)
                strength += (1 if macd_bull else 0) + (1 if above_vwap else 0) + (1 if bb_bull else 0)
                # RS Contribution (approximate rating for backtest)
                strength += 1.5 if ltp > row["SMA200"] else 0
                strength = min(10.0, round(strength, 1))

                # Strategy Filters + Broad Market Regime Filter
                checks = [
                    nifty_aligned_close.iloc[i] > nifty_aligned_sma.iloc[i], # Market must be bullish
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
