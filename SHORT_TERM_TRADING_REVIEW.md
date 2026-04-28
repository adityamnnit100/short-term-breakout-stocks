# Short-Term Trading System Review

Research date: 2026-04-25

## Evidence Reviewed

- SEBI reported on 2024-07-24 that 7 out of 10 individual intraday traders in the equity cash segment made losses.
- SEBI reported on 2024-09-23 that 93% of individual equity F&O traders lost money between FY22 and FY24, with aggregate losses above Rs 1.8 lakh crore. This is derivatives, not cash equity, but it is still useful evidence about overtrading, costs, leverage, and poor risk control.
- Zerodha Varsity's risk-management material emphasizes position sizing as a core part of a trading system and warns against increasing bet size after losing streaks.

## Practical Lessons For Indian Equity Short-Term Trading

Successful short-term equity traders generally have a repeatable edge and strict execution rules:

- Trade liquid stocks with enough participation and avoid thin counters.
- Prefer broad-market and sector support; breakouts work better when breadth is healthy.
- Avoid chasing extended candles where the stop becomes too wide.
- Predefine stop, target, position size, and daily loss limit before entry.
- Rank fewer, higher-quality opportunities instead of increasing trade count.
- Track risk in R multiples so win rate is not viewed in isolation.

## System Review

AlphaScanner already had the right base: trend stack, volume, RSI, ADX, relative strength, VCP/pre-breakout logic, sector momentum, ATR stops, and backtest R metrics.

Main gaps found:

- A scanner bug referenced an undefined `resistance` variable, which could suppress valid candidates.
- Market breadth was calculated but not used in signal scoring.
- The result table did not surface execution risk clearly enough for short-term traders.
- Volume failures in breakout mode were not counted as volume failures.

## Implemented Improvements

- Added market breadth health: `Risk-On`, `Constructive`, `Caution`, `Risk-Off`.
- Added breadth-aware signal scoring, with penalties in weak breadth and bonuses in strong breadth.
- Added execution fields to scan results:
  - `Stop_%`
  - `RR`
  - `Qty_1L_1pct`
  - `Risk_Grade`
  - `Market_Health`
- Added risk grade and breadth context to the setup workspace.
- Added stop, RR, risk grade, and breadth columns to the scanner blotter.
- Fixed the undefined `_Resistance` calculation.
- Counted low-volume breakout candidates under `volume_fail`.

## FII Accumulation Scanner

Added a separate sidebar scanner for stocks where FII holding is reported as increasing quarter-on-quarter. The scanner uses the public Screener.in screen "FII Holding Increasing Quarter on Quarter Basis" as a data source, then applies local filters:

- Market cap at least Rs 1,000 Cr by default.
- Minimum change in FII holding at least 1% by default.
- Ranking score combines FII increase, current FII holding, market cap, ROCE, quarterly profit growth, quarterly sales growth, and reasonable valuation.

This should be treated as a medium-term institutional accumulation watchlist, not an intraday trigger. A chart/price-action confirmation is still needed before entry.

## Suggested Operating Rules

- Prefer `Risk A` and `Risk B` setups.
- Skip or reduce size on `Risk-Off` breadth days.
- Keep per-trade risk near 0.5%-1.0% of account capital.
- Stop trading for the day after the preset daily loss limit is hit.
- Use the backtest tab to evaluate expectancy in R, not only win rate.
