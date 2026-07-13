from __future__ import annotations

import pandas as pd

from quality_filter import QualityContext, QualityFilterEngine
from scanner.config import ScannerConfig


def _make_frame(prices, volumes):
    close = pd.Series(prices)
    return pd.DataFrame(
        {
            "Open": close - 0.1,
            "High": close + 0.5,
            "Low": close - 0.6,
            "Close": close,
            "Volume": pd.Series(volumes),
        }
    )


def test_quality_filter_engine_passes_default_context():
    config = ScannerConfig(min_candles=20)
    engine = QualityFilterEngine(config)
    frame = _make_frame([100 + i * 0.5 for i in range(60)], [1000 + i * 10 for i in range(60)])

    context = engine.build_context(frame, ticker="TEST.NS", sector="Industrials")
    assert context is not None

    result = engine.evaluate(context)

    assert result.passed is True
    assert result.failed_checks == []
    assert "market" in result.details


def test_quality_filter_engine_accumulates_rejections():
    config = ScannerConfig(
        quality_min_avg_volume=10_000.0,
        quality_min_avg_turnover=2_000_000.0,
        quality_min_relative_strength=80.0,
        quality_min_sector_strength=50.0,
        quality_require_price_above_ema200=True,
        quality_require_ema_alignment=True,
        quality_require_trend_template=True,
        quality_require_higher_highs=True,
        quality_require_higher_lows=True,
        quality_market_bearish_multiplier=1.5,
    )
    engine = QualityFilterEngine(config)

    frame = _make_frame([100 - i * 0.4 for i in range(60)], [100 + i for i in range(60)])
    context = engine.build_context(frame, ticker="FAIL.NS", sector="Industrials")
    assert context is not None
    context.market_regime = "BEARISH"
    context.avg_volume = 100.0
    context.avg_turnover = 5_000.0
    context.relative_strength = 40.0
    context.sector_strength = 10.0
    context.latest_close = 75.0
    context.latest_ema20 = 80.0
    context.latest_ema50 = 85.0
    context.latest_ema200 = 90.0
    context.trend_template_pass = False
    context.higher_highs = False
    context.higher_lows = False

    result = engine.evaluate(context)

    assert result.passed is False
    assert "Liquidity Too Low" in result.failed_checks
    assert "Relative Strength Below Threshold" in result.failed_checks
    assert "Weak Sector" in result.failed_checks
    assert "Trend Template Failed" in result.failed_checks
    assert result.rejection_reason
