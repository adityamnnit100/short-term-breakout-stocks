from __future__ import annotations

import importlib

import pandas as pd

from quality_filter import QualityFilterEngine
from scanner.config import ScannerConfig
from setup_engine import SetupEngine


def _setup_frame():
    prices = [100.0] * 20 + [100.5, 100.2, 100.4, 100.3, 100.45, 100.35, 100.4, 100.38, 100.41, 100.39] + [100.4 + i * 0.05 for i in range(30)]
    volumes = [2000] * 20 + [1500, 1450, 1400, 1380, 1360, 1350, 1300, 1280, 1260, 1240] + [1200 - i * 5 for i in range(30)]
    close = pd.Series(prices[:60])
    return pd.DataFrame(
        {
            "Open": close - 0.1,
            "High": close + 0.4,
            "Low": close - 0.5,
            "Close": close,
            "Volume": pd.Series(volumes[:60]),
        }
    )


def test_setup_engine_returns_breakdown_and_category():
    config = ScannerConfig(min_candles=20)
    quality_engine = QualityFilterEngine(config)
    setup_engine = SetupEngine(config)

    context = quality_engine.build_context(_setup_frame(), ticker="SETUP.NS", sector="Industrials")
    assert context is not None

    result = setup_engine.evaluate(context)

    assert result.ticker == "SETUP.NS"
    assert result.setup_score >= 0
    assert result.category in {"Professional", "Excellent", "Good", "Average", "Poor"}
    assert result.base_score >= 0
    assert result.compression_score >= 0
    assert result.volume_score >= 0
    assert result.resistance_score >= 0
    assert result.structure_score >= 0
    assert result.risk_score >= 0
    assert result.metrics


def test_setup_analysis_rows_are_append_only(tmp_path, monkeypatch):
    db_path = tmp_path / "setup_history.db"
    monkeypatch.setenv("ALPHASCANNER_USER_DB", str(db_path))

    import alphascanner_ui.database as database

    database = importlib.reload(database)
    database.init_db()

    rows = [
        {
            "analysis_date": "2026-07-13",
            "ticker": "AAA.NS",
            "scan_mode": "Watchlist",
            "setup_score": 91.0,
            "base_score": 88.0,
            "compression_score": 90.0,
            "volume_score": 84.0,
            "resistance_score": 92.0,
            "structure_score": 89.0,
            "risk_score": 86.0,
            "category": "Professional",
            "reasons": ["Flat base"],
            "weaknesses": ["Base slightly deep"],
        }
    ]

    database.append_setup_analysis_rows(rows)
    database.append_setup_analysis_rows(rows)

    stored = database.execute_query("SELECT COUNT(*) FROM setup_analyses", is_select=True)
    assert stored[0][0] == 2
