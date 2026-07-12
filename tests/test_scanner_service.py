from __future__ import annotations

from pathlib import Path

import pandas as pd

import scanner_service


def test_modular_scan_routes_to_modular_engine(monkeypatch):
    calls = []
    progress_updates = []
    captured = {}

    def fake_run_dual_mode_scan(config=None, output_path=None, progress_callback=None, **kwargs):
        calls.append(config)
        captured.update(kwargs)
        if progress_callback:
            progress_callback(0.5)
            progress_callback(1.0)
        return {
            "watchlist": pd.DataFrame([{"Ticker": "AAA.NS", "Watchlist Score": 80.0}]),
            "entry": pd.DataFrame([{"Ticker": "BBB.NS", "Entry Score": 90.0}]),
        }

    monkeypatch.setattr(scanner_service, "run_dual_mode_scan", fake_run_dual_mode_scan)

    results, stats, scan_time = scanner_service.perform_fresh_scan(
        universe="Nifty 500",
        vol_thresh=1.0,
        rsi_min=50,
        rsi_max=85,
        dist_thresh=1.5,
        min_mkt_cap_cr=0,
        max_mkt_cap_cr=0,
        scanner_type="Modular Momentum",
        scan_mode="Watchlist Scanner",
        timeframe="1d",
        progress_callback=progress_updates.append,
    )

    assert len(calls) == 1
    assert list(results["Ticker"]) == ["AAA.NS"]
    assert stats["scan_mode"] == "Watchlist Scanner"
    assert progress_updates[-1] == 1.0
    assert captured.get("use_cache") is False
    assert scan_time


def test_legacy_scan_routes_to_breakout_engine(monkeypatch):
    import breakout

    captured = {}

    def fake_run_scanner(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame([{"Ticker": "LEGACY.NS", "Signal_Strength": 8.0}]), {"scanner_type": "Breakout"}

    monkeypatch.setattr(breakout, "run_scanner", fake_run_scanner)

    results, stats, scan_time = scanner_service.perform_fresh_scan(
        universe="Nifty 500",
        vol_thresh=1.5,
        rsi_min=50,
        rsi_max=85,
        dist_thresh=1.5,
        min_mkt_cap_cr=0,
        max_mkt_cap_cr=0,
        scanner_type="Breakout",
        scan_mode="Entry Scanner",
        timeframe="1d",
    )

    assert captured["scanner_type"] == "Breakout"
    assert captured["use_cache"] is False
    assert list(results["Ticker"]) == ["LEGACY.NS"]
    assert stats["scanner_type"] == "Breakout"
    assert scan_time


def test_fii_scan_keeps_quarterly_timeframe(monkeypatch):
    import breakout

    captured = {}

    def fake_run_fii_accumulation_scanner(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame([{"Ticker": "FII.NS"}]), {"scanner_type": "FII Accumulation"}

    monkeypatch.setattr(breakout, "run_fii_accumulation_scanner", fake_run_fii_accumulation_scanner)

    results, stats, scan_time = scanner_service.perform_fresh_scan(
        universe="Screener.in FII QoQ",
        vol_thresh=1.0,
        rsi_min=50,
        rsi_max=85,
        dist_thresh=1.5,
        min_mkt_cap_cr=1000,
        max_mkt_cap_cr=0,
        scanner_type="FII Accumulation",
        scan_mode="Entry Scanner",
        timeframe="quarterly",
    )

    assert captured == {"min_mkt_cap_cr": 1000, "min_fii_change_pct": 1.0}
    assert list(results["Ticker"]) == ["FII.NS"]
    assert stats["scanner_type"] == "FII Accumulation"
    assert scan_time


def test_modular_cached_scan_reads_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = Path("data")
    data_dir.mkdir()
    pd.DataFrame([{"Ticker": "CACHED.NS", "Entry Score": 88.0}]).to_csv(data_dir / "entry.csv", index=False)

    results, stats, scan_time = scanner_service.fetch_cached_data(
        use_cache=True,
        universe="Nifty 500",
        scanner_type="Modular Momentum",
        timeframe="1d",
        scan_mode="Entry Scanner",
    )

    assert list(results["Ticker"]) == ["CACHED.NS"]
    assert stats["scan_mode"] == "Entry Scanner"
    assert scan_time
