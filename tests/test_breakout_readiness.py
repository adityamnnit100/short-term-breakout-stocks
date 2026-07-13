from __future__ import annotations

import pandas as pd
import pytest

import scanner_service
import breakout
from breakout_readiness import rank_breakout_readiness
from scanner.indicators import safe_pct_change


def test_modular_scan_normalizes_daily_interval(monkeypatch):
    captured = {}

    def fake_run_dual_mode_scan(config=None, **kwargs):
        captured["interval"] = config.interval
        return {"watchlist": pd.DataFrame(), "entry": pd.DataFrame()}

    monkeypatch.setattr(scanner_service, "run_dual_mode_scan", fake_run_dual_mode_scan)

    scanner_service.perform_fresh_scan(
        universe="Nifty 500",
        vol_thresh=1.0,
        rsi_min=50,
        rsi_max=85,
        dist_thresh=1.5,
        min_mkt_cap_cr=0,
        max_mkt_cap_cr=0,
        scanner_type="Modular Momentum",
        scan_mode="Entry Scanner",
        timeframe="Daily",
    )

    assert captured["interval"] == "1d"


def test_breakout_readiness_engine_ranks_candidates():
    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    close = pd.Series([100 + i * 0.2 + (0.5 if i > 90 else 0) for i in range(120)], index=idx)
    history = pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": pd.Series([2000 - i * 3 if i < 100 else 900 - (i - 100) * 5 for i in range(120)], index=idx),
        }
    )
    scan_results = pd.DataFrame([{"Ticker": "TEST.NS", "Entry Price": float(close.iloc[-1])}])

    ranked = rank_breakout_readiness(
        scan_results,
        history_loader=lambda ticker, period="1y", interval="1d": history,
        benchmark_loader=lambda period="6mo": pd.DataFrame({"Close": close * 1.01}, index=idx),
        max_candidates=8,
        min_score=45.0,
    )

    assert not ranked.empty
    assert ranked.iloc[0]["ticker"] == "TEST.NS"
    assert ranked.iloc[0]["breakout_readiness_score"] >= 45.0


def test_safe_pct_change_reused_by_compression_logic():
    assert safe_pct_change(5.0, 0.0) == 0.0
    assert safe_pct_change(11.0, 10.0) == pytest.approx(10.0)


def test_total_market_universe_includes_microcaps(monkeypatch):
    def fake_fetch_index_symbols(urls, label):
        if label == "Nifty 500":
            return ["AAA.NS", "BBB.NS"]
        if label == "Nifty Microcap 250":
            return ["BBB.NS", "CCC.NS"]
        return []

    monkeypatch.setattr(breakout, "_fetch_index_symbols", fake_fetch_index_symbols)

    symbols = breakout.get_nifty_total_market()

    assert symbols == ["AAA.NS", "BBB.NS", "CCC.NS"]
