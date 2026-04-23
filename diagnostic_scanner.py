#!/usr/bin/env python3
"""
DIAGNOSTIC: AlphaScanner - Trace filter rejections
Run this to see exactly why no stocks are being returned
"""

import yfinance as yf
import pandas as pd
import numpy as np
from breakout import (
    get_nifty_500, calculate_rsi, calculate_adx, calculate_vwap,
    calculate_macd, calculate_bollinger_bands, _scanner_quality_profile,
    detect_vcp_tightness, detect_volume_dryup, get_nifty_total_market,
    calculate_rvol, detect_breakaway_gap
)

def test_scanner_logic(universe="Nifty 500", scanner_type="Breakout", sample_size=20):
    """Test first N stocks to see filter rejections"""
    
    if universe == "Total Market (Cap Focused)":
        tickers = get_nifty_total_market()
    else:
        tickers = get_nifty_500()
    
    print(f"\n{'='*80}")
    print(f"Testing {scanner_type} Scanner on {universe}")
    print(f"Universe size: {len(tickers)} stocks")
    print(f"{'='*80}\n")
    
    # Get Nifty for RS
    try:
        nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty_close = nifty["Close"].dropna()
    except:
        nifty_close = pd.Series()
    
    quality_profile = _scanner_quality_profile(scanner_type, universe)
    dist_thresh = 1.5 if scanner_type == "Breakout" else 5.0
    vol_thresh = 1.5 if scanner_type == "Breakout" else 0.8
    rsi_min, rsi_max = (60, 78) if scanner_type == "Breakout" else (40, 65)
    
    stats = {
        "tested": 0, "passed": 0,
        "trend_fail": 0, "rsi_fail": 0, "volume_fail": 0,
        "adx_fail": 0, "rs_fail": 0, "breakout_fail": 0,
        "liquidity_fail": 0,
    }
    
    results = []
    
    for i, ticker in enumerate(tickers[:sample_size]):
        try:
            stats["tested"] += 1
            df = yf.download(ticker, period="2y", interval="1d", progress=False)
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = df.dropna(subset=["Close", "High", "Low", "Open", "Volume"])
            
            if len(df) < 200:
                print(f"⊗ {ticker}: Insufficient data ({len(df)} bars)")
                continue
            
            ltp = float(df["Close"].iloc[-1])
            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            vol = df["Volume"]
            
            # Filter 0: Liquidity
            avg_vol = float(vol.rolling(30).mean().iloc[-2])
            if ltp < quality_profile["min_price"] or avg_vol < quality_profile["min_avg_volume"]:
                stats["liquidity_fail"] += 1
                print(f"⊗ {ticker} @ ${ltp:.2f}: Liquidity fail (${ltp}, vol {avg_vol:.0f})")
                continue
            
            # Indicators
            sma_200 = close.rolling(200).mean().iloc[-1]
            sma_50 = close.rolling(50).mean().iloc[-1]
            ema_20_ser = close.ewm(span=20, adjust=False).mean()
            ema_20 = ema_20_ser.iloc[-1]
            rsi = calculate_rsi(close).iloc[-1]
            adx = calculate_adx(high, low, close).iloc[-1]
            
            # New Professional Features Sanity
            rvol = calculate_rvol(vol)
            is_breakaway = detect_breakaway_gap(df)
            
            # Extension check
            dist_from_ema = (ltp - ema_20) / max(ema_20, 1e-9) * 100
            is_stretched = dist_from_ema > 5.0
            if is_stretched:
                print(f"! {ticker}: WARNING - Stretched ({dist_from_ema:.1f}% from EMA20)")
                # We don't 'continue' here because we want to see if it passes other filters
            
            # Filter 1: Trend
            trend_ok = (ema_20 > sma_50) and (sma_50 > sma_200)
            if not trend_ok:
                stats["trend_fail"] += 1
                print(f"⊗ {ticker}: Trend fail (EMA {ema_20:.0f} > SMA50 {sma_50:.0f} > SMA200 {sma_200:.0f}? {trend_ok})")
                continue
            
            # Filter 3: RSI
            if not (rsi_min <= rsi <= rsi_max):
                stats["rsi_fail"] += 1
                print(f"⊗ {ticker}: RSI fail ({rsi:.1f} not in {rsi_min}-{rsi_max})")
                continue
            
            # Filter 5: ADX
            adx_min = quality_profile["adx_min"]
            if not (adx > adx_min):
                stats["adx_fail"] += 1
                print(f"⊗ {ticker}: ADX fail ({adx:.1f} <= {adx_min})")
                continue
            
            # Filter 6: Breakout
            prev_h20 = float(high.iloc[-21:-1].max())
            prev_h52 = float(high.iloc[-252:-1].max())
            breakout_buffer = 1 + quality_profile["breakout_buffer_pct"] / 100
            broke_20d = ltp >= prev_h20 * breakout_buffer
            broke_52w = ltp >= prev_h52 * breakout_buffer
            is_breaking_out = broke_20d or broke_52w
            
            # Consolidation check (for Pre-Breakout)
            upper_buffer = 1 + quality_profile["breakout_upper_buffer_pct"] / 100
            near_20d = (prev_h20 * (1 - dist_thresh / 100) <= ltp <= prev_h20 * upper_buffer)
            near_52w = (prev_h52 * (1 - dist_thresh / 100) <= ltp <= prev_h52 * upper_buffer)
            is_consolidating = (near_20d or near_52w)
            
            if scanner_type == "Breakout":
                if not is_breaking_out:
                    stats["breakout_fail"] += 1
                    pct_above_20d = ((ltp / prev_h20) - 1) * 100
                    pct_above_52w = ((ltp / prev_h52) - 1) * 100
                    print(f"⊗ {ticker}: Not breaking out (20D:+{pct_above_20d:.2f}% 52W:+{pct_above_52w:.2f}%, needs +{quality_profile['breakout_buffer_pct']:.2f}%)")
                    continue
            else:  # Pre-Breakout
                if not is_consolidating:
                    stats["breakout_fail"] += 1
                    pct_above = ((ltp / prev_h20) - 1) * 100
                    print(f"⊗ {ticker}: Not consolidating near resistance ({pct_above:.2f}% above 20D, needs {dist_thresh:.1f}% above to +{20:.1f}%)")
                    continue
            
            # Check volume
            vol_ratio = float(vol.iloc[-1]) / max(avg_vol, 1)
            min_vol = vol_thresh if scanner_type == "Breakout" else 0.5
            if vol_ratio < min_vol:
                stats["volume_fail"] += 1
                print(f"⊗ {ticker}: Volume fail ({vol_ratio:.2f}x vs {min_vol:.2f}x needed)")
                continue
            
            # ✅ PASSED ALL FILTERS
            stats["passed"] += 1
            results.append({
                "Ticker": ticker,
                "LTP": ltp,
                "RSI": rsi,
                "ADX": adx,
                "20D_High": prev_h20,
                "52W_High": prev_h52,
                "Above_20D": ((ltp/prev_h20)-1)*100,
                "Above_52W": ((ltp/prev_h52)-1)*100,
                "Vol_x": vol_ratio,
            })
            print(f"✓ {ticker} @ ${ltp:.2f}: RSI={rsi:.1f}, ADX={adx:.1f}, Vol={vol_ratio:.2f}x → PASSED!")
            
        except Exception as e:
            print(f"⊗ {ticker}: Error - {str(e)[:50]}")
            continue
    
    # Summary
    print(f"\n{'='*80}")
    print(f"RESULTS: {stats['passed']}/{stats['tested']} stocks passed")
    print(f"  ↳ Trend fails:        {stats['trend_fail']}")
    print(f"  ↳ RSI fails:          {stats['rsi_fail']}")
    print(f"  ↳ ADX fails:          {stats['adx_fail']}")
    print(f"  ↳ Breakout fails:     {stats['breakout_fail']}")
    print(f"  ↳ Volume fails:       {stats['volume_fail']}")
    print(f"  ↳ Liquidity fails:    {stats['liquidity_fail']}")
    print(f"{'='*80}\n")
    
    if results:
        df_results = pd.DataFrame(results)
        print(df_results.to_string())
    else:
        print("⚠ NO RESULTS - Check which filter is being too strict")

if __name__ == "__main__":
    print("\n🔍 BREAKOUT SCANNER DIAGNOSTIC\n")
    
    # Test Nifty 500 Breakout
    test_scanner_logic("Nifty 500", "Breakout", sample_size=30)
    
    # Test Nifty 500 Pre-Breakout
    test_scanner_logic("Nifty 500", "Pre-Breakout", sample_size=30)
