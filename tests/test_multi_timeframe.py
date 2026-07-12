from __future__ import annotations

import pandas as pd

from multi_timeframe import rank_multi_timeframe_candidates


def test_multi_timeframe_ranks_strong_setup():
    weekly_idx = pd.date_range("2024-01-05", periods=40, freq="W-FRI")
    weekly_close = pd.Series([100 + i * 2 for i in range(40)], index=weekly_idx)
    weekly_df = pd.DataFrame(
        {
            "Open": weekly_close - 0.5,
            "High": weekly_close + 2.0,
            "Low": weekly_close - 2.0,
            "Close": weekly_close,
            "Volume": pd.Series([10000 + i * 100 for i in range(40)], index=weekly_idx),
        }
    )

    hourly_idx = pd.date_range("2025-01-01", periods=80, freq="H")
    hourly_close = pd.Series([200 + i * 0.5 for i in range(80)], index=hourly_idx)
    hourly_df = pd.DataFrame(
        {
            "Open": hourly_close - 0.2,
            "High": hourly_close + 0.6,
            "Low": hourly_close - 0.7,
            "Close": hourly_close,
            "Volume": pd.Series([5000 + i * 20 for i in range(80)], index=hourly_idx),
        }
    )

    def fake_loader(ticker, period="1y", interval="1d"):
        if interval == "1wk":
            return weekly_df
        if interval == "1h":
            return hourly_df
        return weekly_df

    results = pd.DataFrame([{"Ticker": "STRONG.NS", "Entry Score": 88.0, "Sector": "Tech"}])
    ranking = rank_multi_timeframe_candidates(
        results,
        history_loader=fake_loader,
        regime_result={"regime": "BULLISH", "score_multiplier": 1.0, "buy_min_score": 80.0, "score": 82.0, "reasons": []},
        max_candidates=8,
    )

    assert not ranking.empty
    assert ranking.iloc[0]["Ticker"] == "STRONG.NS"
    assert ranking.iloc[0]["Recommendation"] in {"Strong Buy", "Buy", "Watch", "Wait"}
