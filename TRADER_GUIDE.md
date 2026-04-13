# AlphaScanner PRO - Trader's Quick Reference Guide

## 🎯 THE 11-FILTER MOMENTUM SYSTEM

```
┌─────────────────────────────────────────────────────┐
│                 ENTRY SIGNAL FILTERS                │
├─────────────────────────────────────────────────────┤
│ 1️⃣  TREND STACK        │ Price > EMA20 > SMA50 > SMA200
│ 2️⃣  VOLUME CONVICTION  │ Current vol > 1.5× avg volume
│ 3️⃣  MOMENTUM RSI       │ 60 < RSI < 78 (hot zone)
│ 4️⃣  CANDLE QUALITY     │ Close in top 30% of daily range
│ 5️⃣  TREND STRENGTH ADX │ ADX > 20 (not sideways)
│ 6️⃣  BREAKOUT PROXIMITY │ <1.5% from 20D or 52W high
│ 7️⃣  ✨ MACD BULLISH   │ MACD > Signal, histogram +
│ 8️⃣  ✨ BB EXPANSION   │ Price in upper 25% of bands
│ 9️⃣  ✨ VWAP LEVEL     │ Trading above VWAP
│ 🔟 ✨ STOCH RSI       │ 20-80 neutral zone
│ 1️⃣1️⃣ ✨ MA SLOPE     │ Both moving averages rising
└─────────────────────────────────────────────────────┘

✨ = NEW advanced filters
```

### 🧪 NEW: THE PRE-BREAKOUT SCANNER (VCP MODE)

To catch moves *before* they happen, use the **Pre-Breakout** mode. This is specifically designed to find "Launchpad" setups where price is tight and supply is exhausted.

**Recommended Settings for Mid/Small Caps:**
- **Scanner Type**: Pre-Breakout
- **Universe**: Total Market (Cap Focused)
- **Market Cap**: 500Cr - 20,000Cr
- **RSI Range**: 40-65 (Look for accumulation, not extension)
- **Proximity**: 3% - 5% (Distance to 20D or 52W high)

**Key Pre-Breakout Actions:**
- `VCP Setup`: High conviction. Indicates Volatility Contraction Pattern.
- `Near Breakout`: Price is knocking on the door of resistance.
- `Vol-Dryup`: Indicates supply is gone; the path of least resistance is likely up.
- `Setup Score`: A granular 0-10 rating of the base quality (Tightness + RSI Accumulation).
```

---

## 📊 SIGNAL STRENGTH LEGEND (0-10)

Higher score = More confirmation = More reliable

```
🟥 0-2  : Weak (Skip these)
🟩 3-4  : Fair (Use with caution)
🟩 5-6  : Good (Standard entry)
🟩 7-8  : Strong (Preferred)
🟩 9-10 : Excellent (Best-in-class)
```

Example:
- Stock has MACD ✅ + BB ✅ + VWAP ✅ + Divergence ✅ + Vol Spike ✅ = **Score 5/10** High confidence!

---

## 💰 TRADE SETUP FORMULA

```
Entry Price     = Current LTP

Stop Loss       = Entry - (1.5 × ATR)
                  ↓ (Tactical stop for quick exit)

Target 1        = Entry + (1.0 × ATR)
                  ↓ (Book 30% profit, move SL to entry)

Target 2        = Entry + (3.0 × ATR) 
                  ↓ (Main target for 1:2 RR ratio)

Target 3        = Entry + (5.0 × ATR)
                  ↓ (Extended run if momentum continues)

Support 1       = Bollinger Lower Band
                  ↓ (Quick support)

Support 2       = 200-Day SMA
                  ↓ (Strategic support)

Risk Amount     = Entry - Stop Loss
Risk-Reward     = (Target 2 - Entry) / Risk Amount
```

**Example**:
```
Entry: ₹1500
ATR: ₹20
Stop: 1500 - (1.5 × 20) = ₹1470 (Risk ₹30)
Target: 1500 + (3 × 20) = ₹1560 (Reward ₹60)
RR Ratio: 60/30 = 1:2 ✓

If you risk ₹1,000 per trade:
Position size = ₹1,000 / ₹30 = ~33 shares
Max loss: ₹1,000
Max profit (TP2): ₹2,000 (2R)
```

---

## 🚀 OPTIMAL MARKET CONDITIONS

### ✅ BEST FOR THIS SYSTEM
- [ ] Trending markets (ADX > 20)
- [ ] Intraday momentum (08:00-14:00 IST)
- [ ] After volume breakout
- [ ] When multiple indicators align
- [ ] First 30 mins after market open

### ❌ AVOID THESE SITUATIONS
- [ ] Ranging/sideways markets
- [ ] Earnings week for stocks
- [ ] Low volume (< 1× avg)
- [ ] After adverse news
- [ ] Last 30 mins before close

---

## 📱 DAILY ROUTINE

### 08:00 - Market Open
1. Click **"⚡ SCAN NOW"** 
2. Review top 5 stocks by Signal Strength
3. Check charts for visual confirmation
4. Note key resistance/support levels

### 08:30-14:00 - Active Trading
1. Monitor watchlist additions
2. Entry on dip to support OR breakout above resistance
3. Book partial at TP1
4. Trailing stop for TP2+ targets

### 15:00 - End of Day
1. Run backtest with day's parameters
2. Review win rate
3. Note any failures/false signals
4. Adjust filters if needed

### Weekly
1. Check "Filter Analysis" breakdown
2. If too many volume fails → Lower threshold
3. If too many MACD fails → Market trending lower
4. If too many Momentum fails → Market overbought

---

## 🎯 SIGNAL INTERPRETATION

### When You See This → Do This

| Signal | What It Means | Action |
|--------|--------------|--------|
| **Signal Strength 9-10** | Perfect confluence | ENTER |
| **Signal Strength 5-6** | Decent setup | Consider entering |
| **Signal Strength 3-4** | Weak | Wait for better |
| **MACD ✅** | Bullish momentum confirmed | Look for entry |
| **MACD ❌** | Bearish or flat | SKIP |
| **BB ✅** | Volatility break to upside | Momentum likely |
| **BB ❌** | Price compressed | Wait for expansion |
| **VWAP ✅** | Institutions buying | Strong bias |
| **VWAP ❌** | Below volume levels | Skip or short |
| **Vol Spike ✅** | Conviction in move | Real breakout |
| **Divergence Bull** | Price lower, RSI higher | Reversal coming |
| **Divergence Bear** | Price higher, RSI lower | Downtrend warning |

---

## 🛑 RISK MANAGEMENT RULES

### Position Sizing Example

```
Account: ₹1,00,000
Risk per trade: 1% = ₹1,000
Stock ATR: ₹25
Stop Loss distance: 1.5×ATR = ₹37.50

Position size = 1000 / 37.50 = 26 shares
```

### Daily Limits

- **Max trades per day**: 5 (quality over quantity)
- **Max loss per day**: 2% portfolio (₹2,000)
- **Daily profit target**: 1% portfolio (₹1,000)

### Trade Management

- **TP1 (1× ATR)**: Close 30% position, move SL to entry
- **TP2 (3× ATR)**: Close 50% position, trail SL by -1×ATR
- **TP3+ (5× ATR)**: Let winner run with trailing stop

---

## 📈 BACKTEST INTERPRETATION

### Example Results

```
Date Range: Last 30 days
Total Signals: 45
Completed: 35 (25 wins, 10 losses)
Pending: 10

Win Rate = 25/35 = 71.4% ✓ STRONG!

Expected Return (1% risk per trade):
  Wins: 25 × 2% = +50%
  Losses: 10 × 1% = -10%
  Net: +40% on 1% risk basis ✓

vs Nifty 50 Return: +8%
Alpha Generated: +32% ✓ EXCELLENT
```

### What To Do With Results

| Win Rate | Action |
|----------|--------|
| 70%+ | System working, increase size |
| 50-70% | Good, maintain position size |
| 40-50% | Okay but risky, reduce size |
| <40% | System failing, review parameters |

---

## 🔧 PARAMETER TUNING

### If Too Many "Trend Failures"
→ Market is ranging, reduce scanning OR go lower timeframe

### If High "MACD Failures"  
→ Market in bearish trend, add Put strategies OR skip

### If High "Volume Failures"
→ Market dull, increase min volume threshold OR wait

### If High "Momentum Failures"  
→ Market overbought, reduce RSI max threshold

### If Low Signal Strength Stocks
→ Too many filters, relax one (e.g., RSI 50-85 instead of 60-78)

---

## 💡 TRADER PSYCHOLOGY TIPS

1. **Don't FOMO chase**: Wait for Signal Strength > 6
2. **Respect stops**: Never move stop loss below entry
3. **Let winners run**: Use trailing stops, don't exit early
4. **Size down in losses**: After 2 losses, reduce position
5. **Review weekly**: Adjust parameters based on backtest
6. **Trade journal**: Log every trade, note what worked
7. **Best time trading**: 08:30-12:00, avoid last 30 mins
8. **Volume confirms**: Low volume moves are traps

---

## 📞 COMMON QUESTIONS

**Q: How many stocks should I track?**
A: Start with top 5 by Signal Strength, add to watchlist

**Q: What if no signals today?**
A: That's GOOD! Better 0 trades than 5 bad trades

**Q: Why did a stock fail the backtest?**
A: Check if it hit SL or ran out of time. Consider shorter timeframe

**Q: Should I override the filters?**
A: Only if: High volume confirmed + Chart looks bullish + Industry tailwind

**Q: Best time to trade these signals?**
A: Within 2 hours of signal generation (momentum fades)

**Q: What about gaps up?**
A: Perfect! Check for pullback to TP1 area then enter

---

## ⚡ QUICK CHECKLIST BEFORE ENTRY

- [ ] Signal Strength > 5
- [ ] MACD positive  
- [ ] Price above VWAP
- [ ] Volume spike confirmed
- [ ] Chart looks bullish (visual confirmation)
- [ ] RR Ratio > 1:1.5
- [ ] Account risk limit still available
- [ ] Time window: 08:30-14:00 IST

---

## 🎓 LEARNING RESOURCES

**Understand the Indicators**:
- **ADX**: Trend strength (0-100, >20 is trending)
- **MACD**: Momentum confirmation  
- **Bollinger Bands**: Volatility levels
- **VWAP**: Institutional support/resistance
- **RSI**: Overbought/oversold zones
- **ATR**: Volatility measure for stops/targets

**Trade Smarter**:
- Scale into positions (1/3 at entry, 1/3 on breakout, 1/3 on follow)
- Test parameters on backtest before live trading
- Keep trade journal to track patterns
- Adjust for market regime (trending vs ranging)

---

**Remember**: This system is designed for **HIGH WIN RATE + MECHANICAL ENTRIES**. Trust the filters, manage risk, and let the probabilities work over time.

🚀 **Good luck and happy trading!**
