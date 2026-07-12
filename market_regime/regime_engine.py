"""Market regime orchestration."""

from __future__ import annotations

import logging
from typing import Callable, Dict, Iterable, Optional

import pandas as pd

from scanner.config import ScannerConfig
from .breadth import calculate_breadth_metrics
from .market_score import (
    aggregate_market_regime,
    classify_market_regime,
    score_market_momentum,
    score_market_trend,
)
from .models import MarketRegimeResult
from .volatility import score_market_volatility, score_market_volume

logger = logging.getLogger(__name__)


def _default_index_loader(period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    try:
        from utils.yf_cache import cached_download

        df = cached_download("^NSEI", period=period, interval=interval, progress=False, auto_adjust=False, use_cache=True)
        if isinstance(df, pd.DataFrame) and not df.empty and isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _default_universe_loader(config: ScannerConfig) -> Iterable[str]:
    try:
        from breakout import get_nifty_500

        return get_nifty_500()
    except Exception:
        return []


def evaluate_market_regime(
    config: Optional[ScannerConfig] = None,
    index_loader: Optional[Callable[..., pd.DataFrame]] = None,
    universe_loader: Optional[Callable[[ScannerConfig], Iterable[str]]] = None,
    use_cache: bool = True,
) -> Dict[str, object]:
    """Calculate market regime score and classification using NIFTY 50 and NIFTY 500."""
    config = config or ScannerConfig()
    index_loader = index_loader or _default_index_loader
    universe_loader = universe_loader or _default_universe_loader

    index_df = index_loader(period=config.market_regime_nifty50_period, interval="1d")
    if index_df is None or index_df.empty:
        result = MarketRegimeResult(
            score=0.0,
            regime="BEARISH",
            score_multiplier=config.market_regime_bearish_penalty,
            buy_min_score=config.market_regime_buy_min_bearish,
            reasons=["NIFTY 50 data unavailable"],
            components={},
            metrics={},
        )
        return result.to_dict()

    trend_score, trend_metrics, trend_reasons = score_market_trend(index_df, config)
    momentum_score, momentum_metrics, momentum_reasons = score_market_momentum(index_df, config)
    volatility_score, volatility_metrics = score_market_volatility(index_df, config)
    volume_score, volume_metrics = score_market_volume(index_df, config)

    universe = list(universe_loader(config))
    breadth_score, breadth_metrics, breadth_raw = calculate_breadth_metrics(universe, config, use_cache=use_cache)

    regime_score = aggregate_market_regime(
        trend_score=trend_score,
        breadth_score=breadth_score,
        momentum_score=momentum_score,
        volume_score=volume_score,
        volatility_score=volatility_score,
        config=config,
    )
    regime, multiplier, buy_min_score = classify_market_regime(regime_score, config)

    reasons = []
    reasons.extend(trend_reasons[:2])
    reasons.extend(momentum_reasons[:2])
    if breadth_metrics.get("pct_above_ema20", 0.0) >= config.market_regime_breadth_min_above_ema20:
        reasons.append("Breadth expanding")
    if volume_metrics.get("accumulation_days", 0.0) > volume_metrics.get("distribution_days", 0.0):
        reasons.append("Accumulation > distribution")
    if volatility_score >= 70:
        reasons.append("Volatility constructive")

    components = {
        "trend_score": trend_score,
        "breadth_score": breadth_score,
        "momentum_score": momentum_score,
        "volume_score": volume_score,
        "volatility_score": volatility_score,
    }

    metrics: Dict[str, object] = {}
    metrics.update(trend_metrics)
    metrics.update(momentum_metrics)
    metrics.update(breadth_metrics)
    metrics.update(breadth_raw)
    metrics.update(volatility_metrics)
    metrics.update(volume_metrics)

    result = MarketRegimeResult(
        score=regime_score,
        regime=regime,
        score_multiplier=multiplier,
        buy_min_score=buy_min_score,
        reasons=reasons,
        components=components,
        metrics=metrics,
    )
    return result.to_dict()
