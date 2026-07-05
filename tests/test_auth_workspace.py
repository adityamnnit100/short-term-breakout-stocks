from pathlib import Path

from alphascanner_ui import auth, database


def test_workspace_save_and_load_round_trip(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "workspace.db"
    monkeypatch.setattr(auth, "DB_PATH", db_path)
    monkeypatch.setattr(database, "DB_PATH", str(db_path))

    workspace = {
        "watchlist": {"Default": ["AAA.NS", "BBB.NS"], "Momentum": ["CCC.NS"]},
        "portfolio_positions": [
            {
                "ticker": "INFY.NS",
                "entry": 1500.5,
                "stop": 1450.0,
                "shares": 10,
                "risk_amount": 505.0,
                "total_value": 15005.0,
                "date_added": "2026-07-05",
            }
        ],
    }

    auth.save_user_workspace("alice", workspace)
    loaded = auth.load_user_workspace("alice")

    assert loaded["watchlist"] == workspace["watchlist"]
    assert loaded["portfolio_positions"] == workspace["portfolio_positions"]
    assert loaded["risk_positions"] == workspace["portfolio_positions"]
