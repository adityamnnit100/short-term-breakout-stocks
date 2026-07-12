import pandas as pd

from scanner.config import ScannerConfig
import scanner.scanner as scanner_module
from scanner.data import normalize_columns
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


def test_entry_scanner_marks_breakout_setup():
    config = ScannerConfig(min_candles=50)
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

    def fake_batch_download(tickers, config):
        batch_calls.append(list(tickers))
        return {"AAA.NS": history_a, "BBB.NS": history_b}

    def fake_download_history(ticker, config):
        fallback_calls.append(ticker)
        return pd.DataFrame()

    monkeypatch.setattr(scanner_module, "download_history_batch", fake_batch_download)
    monkeypatch.setattr(scanner_module, "download_history", fake_download_history)
    monkeypatch.setattr(scanner_module.WatchlistScanner, "evaluate", lambda self, df, ticker, sector="Unknown": {"passed": False, "score": 0.0})
    monkeypatch.setattr(scanner_module.EntryScanner, "evaluate", lambda self, df, ticker, sector="Unknown": {"passed": False, "score": 0.0})

    results = scanner_module.run_dual_mode_scan(ScannerConfig(min_candles=3))

    assert batch_calls == [["AAA.NS", "BBB.NS"]]
    assert fallback_calls == []
    assert results["watchlist"].empty
    assert results["entry"].empty


def test_run_dual_mode_scan_processes_full_universe(monkeypatch):
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
    monkeypatch.setattr(scanner_module, "download_history", lambda ticker, config, use_cache=True: pd.DataFrame())
    monkeypatch.setattr(scanner_module.WatchlistScanner, "evaluate", lambda self, df, ticker, sector="Unknown": {"passed": True, "score": 65.0, "ticker": ticker})
    monkeypatch.setattr(scanner_module.EntryScanner, "evaluate", lambda self, df, ticker, sector="Unknown": {"passed": True, "score": 75.0, "ticker": ticker})

    results = scanner_module.run_dual_mode_scan(ScannerConfig(min_candles=3))

    assert len(results["watchlist"]) == 160
    assert len(results["entry"]) == 160
