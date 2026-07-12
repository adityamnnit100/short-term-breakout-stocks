# AlphaScanner PRO System Architecture

## Overview

AlphaScanner PRO is a Streamlit-based stock scanning and analysis system for Indian equities. It combines a legacy breakout scanner with a newer modular momentum scanner, plus independent quality layers for market regime, breakout readiness, and multi-timeframe confirmation.

The canonical implementation in this repo is the modular scanner pipeline under `scanner/`, with the Streamlit UI adapting to either modular or legacy result schemas.

## Core Goals

- Find actionable breakout and pre-breakout opportunities.
- Surface early-stage consolidation setups for watchlist monitoring.
- Keep thresholds centralized and configurable.
- Provide clear explanations, risk metrics, and chart context for each result.

## Architecture At A Glance

1. `scanner/data.py` loads market history, benchmark data, and universe membership.
2. `scanner/modes.py` scores stocks in two modes:
   - `WatchlistScanner`
   - `EntryScanner`
3. `scanner/scanner.py` orchestrates the universe scan, ranks results, and writes CSV outputs.
4. `scanner/report.py` handles CSV persistence and CLI summaries.
5. `scanner_service.py` bridges the dashboard to either modular or legacy scan engines and cache paths.
6. `breakout_readiness/` re-ranks scanner output for imminent breakout quality.
7. `market_regime/` scores the broader market environment and applies a confidence multiplier.
8. `multi_timeframe/` confirms candidates across weekly, daily, and 1H structure.
9. `alphascanner_ui/` renders the Streamlit dashboard, including scanner results and scan-mode aware sidebar controls.

## Scanner Modules

### `scanner/config.py`

Central place for thresholds and sizing constants.

Key settings:

- Universe selection
- Minimum candle history
- EMA, ATR, and volume windows
- Watchlist and entry score thresholds
- Relative strength and risk parameters
- Sector blacklist and required OHLCV columns

### `scanner/data.py`

Responsible for market data ingestion.

Capabilities:

- Normalizes Yahoo Finance column layouts
- Downloads price history for tickers
- Downloads benchmark data for relative strength comparisons
- Resolves the scan universe from Nifty lists

### `scanner/modes.py`

Implements the two modular scoring engines.

#### WatchlistScanner

Designed for early accumulation and base-building setups.

Signals emphasize:

- Price above 200 EMA
- Tight base range
- Consolidation duration
- ATR contraction
- Bollinger width contraction
- Volume dry-up
- Improving relative strength

#### EntryScanner

Designed for actionable breakout confirmation.

Signals emphasize:

- EMA alignment
- Breakout confirmation
- Breakout volume strength
- Relative strength rank
- Sector strength
- ATR and extension risk

Both scanners return structured dictionaries with:

- ticker
- score
- passed
- reasons
- reason text
- trade quality
- setup ID
- recommendation
- confidence

### `scanner/scanner.py`

Top-level orchestration.

What it does:

- Loads the universe
- Downloads price history per ticker
- Runs both scanners
- Renames fields for UI and CSV consistency
- Writes:
  - `data/watchlist.csv`
  - `data/entry.csv`
  - `data/rejected.csv`

The modular scan path returns two DataFrames, one for watchlist candidates and one for entry candidates. The dashboard selects the appropriate frame based on `Scan Mode`.

### `scanner/report.py`

Reporting and CLI formatting.

- Saves result frames to CSV
- Prints a concise console summary
- Supports both modular and legacy result schemas

### `breakout_readiness/`

Independent engine that re-scores the current scanner output for near-term breakout potential.

Signals emphasize:

- Compression and volatility contraction
- Distance to nearest resistance
- Volume dry-up
- Candle tightness
- Relative strength acceleration
- Breakout pressure and confluence

### `market_regime/`

Independent market filter that scores the broader environment using:

- NIFTY 50 trend and momentum
- NIFTY 500 breadth
- Market volatility and volume behavior

Output includes:

- Market regime score from 0 to 100
- Regime classification: `BULLISH`, `NEUTRAL`, `CAUTION`, `BEARISH`
- Buy-floor adjustment and score multiplier for downstream scanners

### `multi_timeframe/`

Independent confirmation layer that evaluates:

- Weekly trend and structure
- Daily scanner output without duplicating calculations
- 1H entry timing and consolidation

Output includes:

- Weekly score
- Daily score
- 1H score
- Final score from 0 to 100
- Recommendation: `Strong Buy`, `Buy`, `Watch`, `Wait`, `Avoid`

## UI Architecture

### Streamlit Entry Point

`dashboard.py` is the app entry point. It wires together the sidebar, tabs, charts, and data services.

### Scanner Tab

`alphascanner_ui/tabs/scanner.py` now supports:

- Modular results
- Legacy breakout-style results
- Market Regime Engine panel
- Breakout Readiness panel
- Multi-Timeframe Confirmation panel
- Filter controls that branch based on schema
- A status banner
- Summary metrics
- Top picks cards
- A blotter and detailed setup workspace

The sidebar controls are wired as follows:

- `Scanner Type` chooses the engine family.
- `Scan Mode` only applies when `Scanner Type` is `Modular Momentum`.
- `Universe` is stored as the effective universe actually used by the scan, including special overrides like `FII Accumulation` and `Long-Term`.

### Modular UI Behavior

The modular scanner UI expects title-cased columns such as:

- `Watchlist Score`
- `Entry Score`
- `Sector`
- `Trade Quality`
- `Recommendation`
- `Setup ID`

Legacy paths still use fields like:

- `Signal_Strength`
- `Risk_Grade`
- `Market_Health`
- `Stop_%`

## Data Flow

1. User selects a scanner mode and universe in the sidebar.
2. The UI calls `scanner_service.fetch_cached_data(...)` or `scanner_service.perform_fresh_scan(...)` depending on the cache toggle.
3. `scanner_service.py` routes `Modular Momentum` to `scanner.run_dual_mode_scan(...)` and legacy scanner types to `breakout.run_scanner(...)` or `breakout.run_fii_accumulation_scanner(...)`.
4. `scanner_service.py` also reads modular cache files from `data/entry.csv` or `data/watchlist.csv`.
5. Results are saved to CSV and returned to the UI.
6. The scanner tab filters and renders the final results.
7. Optional overlays in the UI run the breakout readiness, market regime, and multi-timeframe engines against the current scan output.

## Output Files

- `data/watchlist.csv`: early-stage setups
- `data/entry.csv`: actionable entries
- `data/rejected.csv`: near misses
- `data/scanner_results.csv`: legacy/general scanner export

## Risk and Trade Management

The system includes ATR-based trade planning and risk controls.

Common outputs:

- Entry price
- Stop loss
- Risk percentage
- Target 1
- Target 2
- Risk/reward
- Trade quality
- Position sizing support in the UI

The broader UI also includes:

- Risk tab
- Portfolio tab
- Journal tab
- Alerts services

Watchlist and risk positions are persisted through the database-backed workspace helpers in `alphascanner_ui/auth.py` and `alphascanner_ui/database.py`.

## Charts and Presentation

`alphascanner_ui/charts.py` handles:

- Candlestick chart rendering
- Plotly theming
- Modular top-picks cards
- Legacy scanner table styling

## Environment Notes

- Python 3.8 is supported in the current workspace.
- The repo includes a local virtual environment under `trading_env/`.
- `multitasking` and `yfinance` compatibility matters for the Streamlit app and data downloads.

## Current Limitations

- Sector mapping is still simplified in the modular scanner path.
- The modular scanner now scans the full configured universe, so runtime depends on universe size and data availability.
- Some legacy UI tabs still expect breakout-era fields.
- Intraday scanning is not implemented here; the system is daily-bar focused.
- `Scan Mode` is intentionally modular-only; legacy scanners always behave like entry-style scans.
- Market Regime and Multi-Timeframe are independent overlays and can be enabled without changing the core scanner pipeline.

## Canonical Files

Use these files as the source of truth for the current modular system:

- `scanner/config.py`
- `scanner/data.py`
- `scanner/modes.py`
- `scanner/scanner.py`
- `scanner/report.py`
- `breakout_readiness/`
- `market_regime/`
- `multi_timeframe/`
- `alphascanner_ui/tabs/scanner.py`
- `alphascanner_ui/charts.py`
