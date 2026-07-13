from __future__ import annotations

import importlib

import pandas as pd

from quality_filter import QualityFilterEngine
from scanner.config import ScannerConfig
from setup_engine import SetupEngine
from transition_engine import TransitionEngine
from trigger_engine import TriggerEngine


def _trigger_frame():
    prices = [100.0 + i * 0.35 for i in range(70)]
    prices[-3:] = [122.0, 124.0, 127.5]
    volumes = [1600 + i * 5 for i in range(60)] + [2800, 3600, 5200, 6800, 8000, 9400, 11000, 12500, 15000, 18000]
    close = pd.Series(prices)
    return pd.DataFrame(
        {
            "Open": close - 0.25,
            "High": close + 0.8,
            "Low": close - 0.9,
            "Close": close,
            "Volume": pd.Series(volumes),
        }
    )


def test_trigger_engine_returns_decision_and_breakdown():
    config = ScannerConfig(min_candles=20, trigger_enable_intraday_confirmation=False)
    quality_engine = QualityFilterEngine(config)
    setup_engine = SetupEngine(config)
    transition_engine = TransitionEngine(config)
    trigger_engine = TriggerEngine(config)

    context = quality_engine.build_context(_trigger_frame(), ticker="TRIG.NS", sector="Industrials")
    assert context is not None

    setup_result = setup_engine.evaluate(context)
    transition_result = transition_engine.evaluate(transition_engine.build_context(context, setup_result, scan_mode="Entry"))
    trigger_context = trigger_engine.build_context(context, setup_result, transition_result, scan_mode="Entry")
    result = trigger_engine.evaluate(trigger_context)

    assert result.ticker == "TRIG.NS"
    assert result.decision in {"BUY NOW", "EARLY BUY", "WATCH", "WAIT"}
    assert result.confidence in {"Very High", "High", "Medium", "Low"}
    assert isinstance(result.qualifies, bool)
    assert result.module_results
    assert "pocket_pivot" in result.module_results
    assert "relative_volume" in result.module_results
    assert result.priority_score >= 0.0
    assert 0.0 <= result.rank_percentile <= 100.0


def test_trigger_analysis_rows_are_append_only(tmp_path, monkeypatch):
    db_path = tmp_path / "trigger_history.db"
    monkeypatch.setenv("ALPHASCANNER_USER_DB", str(db_path))

    import alphascanner_ui.database as database

    database = importlib.reload(database)
    database.init_db()

    rows = [
        {
            "analysis_date": "2026-07-13",
            "ticker": "AAA.NS",
            "scan_mode": "Entry",
            "trigger_decision": "BUY",
            "trigger_confidence": "Very High",
            "trigger_score": 92.0,
            "trigger_qualifies": True,
            "trigger_reasons": ["Pocket pivot confirmed"],
            "trigger_weaknesses": [],
            "trigger_module_results": {"pocket_pivot": {"passed": True}},
            "trigger_metrics": {"pocket_pivot": {"volume_ratio": 2.1}},
        }
    ]

    database.append_trigger_analysis_rows(rows)
    database.append_trigger_analysis_rows(rows)

    stored = database.execute_query("SELECT COUNT(*) FROM trigger_analyses", is_select=True)
    assert stored[0][0] == 2
