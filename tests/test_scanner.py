import pytest
import pandas as pd

from scanner.config import ScannerConfig
import scanner.scanner as scanner_module
from scanner.data import normalize_columns
from scanner.formatting import build_reason_label, build_reason_text, confidence, recommendation, setup_id, trade_quality
from scanner.indicators import safe_pct_change
from scanner.modes import EntryScanner, WatchlistScanner


def test_normalize_columns_handles_yfinance_multiindex():
    columns = pd.MultiIndex.from_product([["Open", "High", "Low", "Close", "Volume"], ["RELIANCE.NS"]])
    df = pd.DataFrame([[1, 2, 3, 4, 5]], columns=columns)

    normalized = normalize_columns(df)

    assert list(normalized.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_watchlist_scanner_marks_consolidation_setup():
    config = ScannerConfig(min_candles=50)
    scanner = WatchlistScanner(config)
    prices = [100 + i * 0.15 for i in range(120)]
    closes = pd.Series(prices)
    highs = closes + 0.8
    lows = closes - 0.8
    opens = closes - 0.1
    volumes = [1000 + i * 10 for i in range(120)]
    df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes})

    result = scanner.evaluate(df, ticker="TEST.NS", sector="Industrials")

    assert result["passed"] is True
    assert result["score"] >= config.watchlist_min_score
    assert result["reasons"]
    assert result["trade_quality"] in {"A+", "A", "B", "C", "Reject"}
    assert result["setup_id"]
    assert result["recommendation"]
    assert "setup_score" in result
    assert "setup_category" in result
    assert "setup_base_score" in result
    assert "transition_score" in result
    assert "transition_category" in result
    assert "trigger_decision" in result
    assert "trigger_confidence" in result


def test_entry_scanner_marks_breakout_setup():
    config = ScannerConfig(
        min_candles=50,
        trigger_min_setup_score=55.0,
        trigger_min_transition_score=40.0,
        trigger_min_trigger_score=45.0,
        trigger_buy_now_top_percentile=60.0,
        trigger_early_buy_top_percentile=70.0,
        trigger_watch_top_percentile=80.0,
        trigger_breakout_buffer_pct=-1.0,
        trigger_breakout_volume_ratio_min=1.0,
        trigger_relative_volume_5d_min=0.9,
        trigger_relative_volume_10d_min=0.9,
        trigger_relative_volume_20d_min=0.9,
        trigger_close_strength_min=0.45,
        trigger_pocket_pivot_close_location_min=0.45,
        trigger_rs_proxy_min=90.0,
        trigger_rs_transition_min=20.0,
        trigger_volume_transition_min=20.0,
    )
    scanner = EntryScanner(config)
    prices = [100 + i * 0.5 for i in range(120)]
    closes = pd.Series(prices)
    highs = closes + 0.8
    lows = closes - 0.8
    opens = closes - 0.1
    volumes = [2000 + i * 50 for i in range(120)]
    df = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes})

    result = scanner.evaluate(df, ticker="TEST.NS", sector="Industrials")

    assert result["passed"] is True
    assert result["score"] >= config.entry_min_score
    assert "Breakout" in result["reason_label"]
    assert "setup_score" in result
    assert "setup_compression_score" in result
    assert "transition_score" in result
    assert "trigger_decision" in result


def test_run_dual_mode_scan_uses_batch_download(monkeypatch):
    monkeypatch.setattr(scanner_module, "get_universe", lambda config: ["AAA.NS", "BBB.NS"])

    batch_calls = []
    fallback_calls = []

    history_a = pd.DataFrame(
        {
            "Open": [1, 2, 3, 4, 5],
            "High": [2, 3, 4, 5, 6],
            "Low": [0.5, 1.5, 2.5, 3.5, 4.5],
            "Close": [1.5, 2.5, 3.5, 4.5, 5.5],
            "Volume": [100, 110, 120, 130, 140],
        }
    )
    history_b = history_a.copy()

    def fake_batch_download(tickers, config, use_cache=False):
        batch_calls.append(list(tickers))
        return {"AAA.NS": history_a, "BBB.NS": history_b}

    monkeypatch.setattr(scanner_module, "download_history_batch", fake_batch_download)
    monkeypatch.setattr(
        scanner_module.WatchlistScanner,
        "evaluate",
        lambda self, df, ticker, sector="Unknown", **kwargs: {"passed": False, "score": 0.0},
    )
    monkeypatch.setattr(
        scanner_module.EntryScanner,
        "evaluate",
        lambda self, df, ticker, sector="Unknown", **kwargs: {"passed": False, "score": 0.0},
    )

    results = scanner_module.run_dual_mode_scan(ScannerConfig(min_candles=3))

    assert batch_calls == [["AAA.NS", "BBB.NS"]]
    assert fallback_calls == []
    assert results["watchlist"].empty
    assert results["entry"].empty


def test_run_dual_mode_scan_processes_full_universe(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    tickers = [f"T{i}.NS" for i in range(160)]
    monkeypatch.setattr(scanner_module, "get_universe", lambda config: tickers)

    def fake_batch_download(chunk, config, use_cache=True):
        frame = pd.DataFrame(
            {
                "Open": [1, 2, 3],
                "High": [2, 3, 4],
                "Low": [0.5, 1.5, 2.5],
                "Close": [1.5, 2.5, 3.5],
                "Volume": [100, 110, 120],
            }
        )
        return {ticker: frame for ticker in chunk}

    monkeypatch.setattr(scanner_module, "download_history_batch", fake_batch_download)
    monkeypatch.setattr(
        scanner_module.WatchlistScanner,
        "evaluate",
        lambda self, df, ticker, sector="Unknown", **kwargs: {"passed": True, "score": 65.0, "ticker": ticker},
    )
    monkeypatch.setattr(
        scanner_module.EntryScanner,
        "evaluate",
        lambda self, df, ticker, sector="Unknown", **kwargs: {"passed": True, "score": 75.0, "ticker": ticker, "trigger_qualifies": True, "trigger_module_results": {}},
    )
    monkeypatch.setattr(scanner_module.TriggerEngine, "rank_candidate_rows", lambda self, rows: rows)

    results = scanner_module.run_dual_mode_scan(ScannerConfig(min_candles=3))

    assert len(results["watchlist"]) == 160
    assert len(results["entry"]) == 160


def test_run_dual_mode_scan_records_diagnostics(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    tickers = ["AAA.NS", "BBB.NS", "CCC.NS"]
    monkeypatch.setattr(scanner_module, "get_universe", lambda config: tickers)

    frame = pd.DataFrame(
        {
            "Open": [1, 2, 3, 4],
            "High": [2, 3, 4, 5],
            "Low": [0.5, 1.5, 2.5, 3.5],
            "Close": [1.5, 2.5, 3.5, 4.5],
            "Volume": [100, 110, 120, 130],
        }
    )

    monkeypatch.setattr(scanner_module, "download_history_batch", lambda chunk, config, use_cache=True: {ticker: frame for ticker in chunk})
    monkeypatch.setattr(
        scanner_module.WatchlistScanner,
        "evaluate",
        lambda self, df, ticker, sector="Unknown", **kwargs: {"passed": True, "score": 65.0, "ticker": ticker},
    )
    monkeypatch.setattr(scanner_module.TriggerEngine, "rank_candidate_rows", lambda self, rows: rows)

    entry_payloads = {
        "AAA.NS": {
            "ticker": "AAA.NS",
            "passed": False,
            "score": 0.0,
            "quality_passed": False,
            "quality_failed_checks": ["Liquidity Too Low"],
            "quality_passed_checks": [],
            "quality_details": {
                "liquidity": {
                    "avg_volume": 100.0,
                    "min_avg_volume": 1000.0,
                }
            },
            "quality_gate_results": {},
        },
        "BBB.NS": {
            "ticker": "BBB.NS",
            "passed": False,
            "score": 55.0,
            "quality_passed": True,
            "quality_failed_checks": [],
            "quality_passed_checks": ["liquidity"],
            "quality_details": {},
            "quality_gate_results": {},
            "setup_qualifies": False,
            "setup_gate_results": {
                "compression": {"passed": False, "score": 32.0, "metrics": {"atr_contraction_pct": -3.0}}
            },
            "setup_metrics": {"compression": {"atr_contraction_pct": -3.0}},
            "transition_qualifies": False,
        },
        "CCC.NS": {
            "ticker": "CCC.NS",
            "passed": True,
            "score": 78.0,
            "quality_passed": True,
            "quality_failed_checks": [],
            "quality_passed_checks": ["liquidity"],
            "quality_details": {},
            "quality_gate_results": {},
            "setup_qualifies": True,
            "setup_gate_results": {
                "compression": {"passed": True, "score": 76.0, "metrics": {}},
            },
            "setup_metrics": {"compression": {}},
            "transition_qualifies": True,
            "transition_gate_results": {},
            "transition_metrics": {},
            "trigger_decision": "WAIT",
            "trigger_confidence": "Low",
            "trigger_module_results": {
                "breakout_confirmation": {"passed": False, "score": 20.0, "metrics": {"close_strength": 74.0}},
                "relative_volume": {"passed": True, "score": 90.0, "metrics": {"rvol": 1.4}},
            },
            "trigger_metrics": {"breakout_confirmation": {"close_strength": 74.0}},
            "trigger_hard_gate_failures": ["Breakout confirmation failed"],
        },
    }

    monkeypatch.setattr(
        scanner_module.EntryScanner,
        "evaluate",
        lambda self, df, ticker, sector="Unknown", **kwargs: entry_payloads[ticker],
    )

    results = scanner_module.run_dual_mode_scan(ScannerConfig(min_candles=3, diagnostics_enabled=True))

    diagnostics = results["diagnostics"]
    assert diagnostics["stages"]["quality"] == {"passed": 2, "rejected": 1}
    assert diagnostics["stages"]["setup"]["rejected"] == 1
    assert diagnostics["decisions"]["WAIT"] == 1
    assert any(item["rule"] == "Liquidity Too Low" for item in diagnostics["most_restrictive_rules"])


def test_shared_scanner_label_helpers_match_mode_expectations():
    reasons = ["EMA alignment", "Breakout confirmed"]

    assert build_reason_label(reasons) == "EMA alignment, Breakout confirmed"
    assert build_reason_label([]) == "No clear signal"
    assert build_reason_text(reasons, 88.456) == "Score: 88.5\nReasons:\n✔ EMA alignment\n✔ Breakout confirmed"
    assert trade_quality(95) == "A+"
    assert trade_quality(80) == "B"
    assert setup_id(88, reasons) == "S1 Early Accumulation + S5 Breakout"
    assert recommendation(92, reasons) == "Buy"
    assert confidence(79) == "Medium"


def test_safe_pct_change_handles_zero_reference():
    assert safe_pct_change(10.0, 0.0) == 0.0
    assert safe_pct_change(12.0, 10.0) == pytest.approx(20.0)
