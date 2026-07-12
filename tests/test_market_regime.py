from __future__ import annotations

import pandas as pd

from market_regime import evaluate_market_regime
import market_regime.breadth as breadth_module


def test_market_regime_scores_and_classifies(monkeypatch):
    idx = pd.date_range("2025-01-01", periods=240, freq="D")
    close = pd.Series([100 + i * 0.3 for i in range(240)], index=idx)
    index_df = pd.DataFrame(
        {
            "Open": close - 0.1,
            "High": close + 0.7,
            "Low": close - 1.0,
            "Close": close,
            "Volume": pd.Series([100000 + i * 100 for i in range(240)], index=idx),
        }
    )

    def fake_incremental_download(tickers, **kwargs):
        idx2 = pd.date_range("2025-01-01", periods=240, freq="D")
        data = {}
        for ticker in tickers:
            series = pd.Series([50 + i * 0.2 for i in range(240)], index=idx2)
            data[("Open", ticker)] = series - 0.1
            data[("High", ticker)] = series + 0.5
            data[("Low", ticker)] = series - 0.6
            data[("Close", ticker)] = series
            data[("Volume", ticker)] = pd.Series([50000 + i * 50 for i in range(240)], index=idx2)
        columns = pd.MultiIndex.from_tuples(data.keys())
        return pd.DataFrame(data, index=idx2, columns=columns)

    monkeypatch.setattr(breadth_module, "incremental_cached_download", fake_incremental_download)

    result = evaluate_market_regime(
        index_loader=lambda period="2y", interval="1d": index_df,
        universe_loader=lambda config: ["AAA.NS", "BBB.NS", "CCC.NS"],
        use_cache=False,
    )

    assert result["regime"] in {"BULLISH", "NEUTRAL"}
    assert result["score"] > 0
    assert "trend_score" in result["components"]
    assert "pct_above_ema20" in result["metrics"]
