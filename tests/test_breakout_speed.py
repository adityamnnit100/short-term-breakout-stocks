from __future__ import annotations

from pathlib import Path

import pandas as pd

import breakout
import utils.yf_cache as yf_cache
from scanner.config import ScannerConfig
import scanner.data as scanner_data


def test_breakout_scan_skips_metadata_prefetch_without_market_cap_filter(monkeypatch):
    calls = []

    monkeypatch.setattr(breakout, "get_nifty_500", lambda: ["AAA.NS"])
    monkeypatch.setattr(
        breakout,
        "_build_market_context",
        lambda: {
            "market_bias": "Neutral",
            "market_bias_score": 0.0,
            "fii_net": 0.0,
            "dii_net": 0.0,
            "nifty_change": 0.0,
            "bank_nifty_change": 0.0,
        },
    )

    benchmark = pd.DataFrame({"Close": [100.0] * 300}, index=pd.date_range("2025-01-01", periods=300, freq="D"))
    monkeypatch.setattr(yf_cache, "cached_download", lambda *args, **kwargs: benchmark)

    def fake_incremental_cached_download(tickers, **kwargs):
        idx = pd.date_range("2025-01-01", periods=300, freq="D")
        data = pd.DataFrame(
            {
                ("Open", "AAA.NS"): [100.0] * 300,
                ("High", "AAA.NS"): [101.0] * 300,
                ("Low", "AAA.NS"): [99.0] * 300,
                ("Close", "AAA.NS"): [100.5] * 300,
                ("Volume", "AAA.NS"): [100000.0] * 300,
            },
            index=idx,
        )
        return data

    monkeypatch.setattr(yf_cache, "incremental_cached_download", fake_incremental_cached_download)
    monkeypatch.setattr(breakout, "prefetch_metadata", lambda tickers: calls.append(list(tickers)))
    monkeypatch.setattr(breakout, "get_all_metadata_cache", lambda tickers, expiry_hours=24: {})
    monkeypatch.setattr(
        breakout,
        "_process_single_ticker",
        lambda *args, **kwargs: {"Ticker": args[0], "Signal_Strength": 5.0},
    )

    results, stats = breakout.run_scanner(
        vol_thresh=1.5,
        rsi_min=50,
        rsi_max=90,
        dist_thresh=1.5,
        min_mkt_cap_cr=0,
        max_mkt_cap_cr=0,
        scanner_type="Breakout",
        universe="Nifty 500",
        timeframe="1d",
        sector_map=None,
        include_news_sentiment=False,
        progress_callback=None,
        incremental_fetch=False,
    )

    assert calls == []
    assert isinstance(results, pd.DataFrame)
    assert stats["scanner_type"] == "Breakout"


def test_breakout_scan_uses_single_batch_download(monkeypatch):
    batch_calls = []

    monkeypatch.setattr(breakout, "get_nifty_500", lambda: ["AAA.NS", "BBB.NS", "CCC.NS"])
    monkeypatch.setattr(
        breakout,
        "_build_market_context",
        lambda: {
            "market_bias": "Neutral",
            "market_bias_score": 0.0,
            "fii_net": 0.0,
            "dii_net": 0.0,
            "nifty_change": 0.0,
            "bank_nifty_change": 0.0,
        },
    )
    monkeypatch.setattr(breakout, "prefetch_metadata", lambda tickers: None)
    monkeypatch.setattr(breakout, "get_all_metadata_cache", lambda tickers, expiry_hours=24: {})
    def fake_download_history_batch(tickers, config, use_cache=True):
        batch_calls.append(list(tickers))
        idx = pd.date_range("2025-01-01", periods=300, freq="D")
        frame = pd.DataFrame(
            {
                "Open": [100.0] * 300,
                "High": [101.0] * 300,
                "Low": [99.0] * 300,
                "Close": [100.5] * 300,
                "Volume": [100000.0] * 300,
            },
            index=idx,
        )
        return {ticker: frame for ticker in tickers}

    monkeypatch.setattr(scanner_data, "download_history_batch", fake_download_history_batch)
    monkeypatch.setattr(
        breakout,
        "_process_single_ticker",
        lambda *args, **kwargs: {"Ticker": args[0], "Signal_Strength": 5.0},
    )

    results, stats = breakout.run_scanner(
        vol_thresh=1.5,
        rsi_min=50,
        rsi_max=90,
        dist_thresh=1.5,
        min_mkt_cap_cr=0,
        max_mkt_cap_cr=0,
        scanner_type="Breakout",
        universe="Nifty 500",
        timeframe="1d",
        sector_map=None,
        include_news_sentiment=False,
        progress_callback=None,
        incremental_fetch=False,
    )

    assert batch_calls == [["AAA.NS", "BBB.NS", "CCC.NS"]]
    assert len(results) == 3
    assert stats["scanned"] == 0


def test_download_history_batch_does_not_use_disk_cache_in_fresh_mode(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [100000.0, 110000.0, 120000.0],
        },
        index=pd.date_range("2025-01-01", periods=3, freq="D"),
    )
    frame.to_pickle(cache_dir / "yf_AAA_NS_1d.pkl")

    monkeypatch.setattr(scanner_data, "cached_download", lambda *args, **kwargs: pd.DataFrame())

    result = scanner_data.download_history_batch(["AAA.NS"], ScannerConfig(interval="1d"), use_cache=False)

    assert result == {}
