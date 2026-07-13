from __future__ import annotations

import importlib

import pandas as pd

from quality_filter import QualityFilterEngine
from scanner.config import ScannerConfig
from setup_engine import SetupEngine
from transition_engine import TransitionEngine


def _transition_frame():
    prices = [100.0 + i * 0.25 for i in range(80)]
    volumes = [2000 - i * 5 for i in range(40)] + [1800 + i * 15 for i in range(40)]
    close = pd.Series(prices)
    return pd.DataFrame(
        {
            "Open": close - 0.1,
            "High": close + 0.45,
            "Low": close - 0.5,
            "Close": close,
            "Volume": pd.Series(volumes),
        }
    )


def test_transition_engine_uses_setup_history_and_returns_breakdown(tmp_path, monkeypatch):
    db_path = tmp_path / "transition_history.db"
    monkeypatch.setenv("ALPHASCANNER_USER_DB", str(db_path))

    import alphascanner_ui.database as database

    database = importlib.reload(database)
    database.init_db()
    database.append_setup_analysis_rows(
        [
            {
                "analysis_date": "2026-07-10",
                "ticker": "TRANS.NS",
                "scan_mode": "Watchlist",
                "setup_score": 61.0,
                "base_score": 58.0,
                "compression_score": 54.0,
                "volume_score": 53.0,
                "resistance_score": 55.0,
                "structure_score": 56.0,
                "risk_score": 52.0,
                "category": "Average",
                "reasons": ["Starting base"],
                "weaknesses": [],
            },
            {
                "analysis_date": "2026-07-11",
                "ticker": "TRANS.NS",
                "scan_mode": "Watchlist",
                "setup_score": 69.0,
                "base_score": 63.0,
                "compression_score": 61.0,
                "volume_score": 58.0,
                "resistance_score": 64.0,
                "structure_score": 62.0,
                "risk_score": 57.0,
                "category": "Good",
                "reasons": ["Base improving"],
                "weaknesses": [],
            },
            {
                "analysis_date": "2026-07-12",
                "ticker": "TRANS.NS",
                "scan_mode": "Watchlist",
                "setup_score": 78.0,
                "base_score": 70.0,
                "compression_score": 69.0,
                "volume_score": 66.0,
                "resistance_score": 72.0,
                "structure_score": 71.0,
                "risk_score": 64.0,
                "category": "Good",
                "reasons": ["Compression improving"],
                "weaknesses": [],
            },
        ]
    )

    config = ScannerConfig(min_candles=20)
    quality_engine = QualityFilterEngine(config)
    setup_engine = SetupEngine(config)
    transition_engine = TransitionEngine(config)

    context = quality_engine.build_context(_transition_frame(), ticker="TRANS.NS", sector="Industrials")
    assert context is not None

    setup_result = setup_engine.evaluate(context)
    transition_context = transition_engine.build_context(context, setup_result, scan_mode="Watchlist")
    result = transition_engine.evaluate(transition_context)

    assert result.ticker == "TRANS.NS"
    assert result.scan_mode == "Watchlist"
    assert result.transition_score >= 0
    assert result.setup_velocity_score >= 0
    assert result.rs_acceleration_score >= 0
    assert result.volume_transition_score >= 0
    assert result.compression_evolution_score >= 0
    assert result.opportunity_velocity_score >= 0
    assert result.category in {"Professional", "Strong", "Building", "Watch", "Weak"}
    assert result.metrics
    assert "setup_velocity" in result.metrics


def test_transition_analysis_rows_are_append_only(tmp_path, monkeypatch):
    db_path = tmp_path / "transition_analysis.db"
    monkeypatch.setenv("ALPHASCANNER_USER_DB", str(db_path))

    import alphascanner_ui.database as database

    database = importlib.reload(database)
    database.init_db()

    rows = [
        {
            "analysis_date": "2026-07-13",
            "ticker": "AAA.NS",
            "scan_mode": "Watchlist",
            "transition_score": 88.0,
            "transition_category": "Strong",
            "transition_setup_velocity_score": 90.0,
            "transition_rs_acceleration_score": 86.0,
            "transition_volume_transition_score": 84.0,
            "transition_compression_evolution_score": 82.0,
            "transition_resistance_pressure_score": 79.0,
            "transition_price_acceptance_score": 81.0,
            "transition_opportunity_velocity_score": 87.0,
            "transition_reasons": ["Improving"],
            "transition_weaknesses": ["Needs confirmation"],
            "transition_qualifies": True,
            "transition_metrics": {"setup_velocity_score": 90.0},
        }
    ]

    database.append_transition_analysis_rows(rows)
    database.append_transition_analysis_rows(rows)

    stored = database.execute_query("SELECT COUNT(*) FROM transition_analyses", is_select=True)
    assert stored[0][0] == 2
