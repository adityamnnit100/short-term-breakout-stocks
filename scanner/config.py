"""Configuration module for the modular momentum scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class ScannerConfig:
    """All scanner thresholds are configurable and centralised here."""

    universe: str = "Nifty 500"
    min_candles: int = 300
    interval: str = "1d"
    lookback_period: str = "2y"
    max_candidates: int = 15
    min_total_score: float = 25.0

    watchlist_min_score: float = 60.0
    entry_min_score: float = 70.0

    watchlist_trend_weight: float = 0.20
    watchlist_base_weight: float = 0.35
    watchlist_volume_weight: float = 0.20
    watchlist_rs_weight: float = 0.15
    watchlist_sector_weight: float = 0.10

    entry_trend_weight: float = 0.20
    entry_breakout_weight: float = 0.25
    entry_volume_weight: float = 0.20
    entry_rs_weight: float = 0.15
    entry_sector_weight: float = 0.15
    entry_risk_weight: float = 0.10

    watchlist_price_above_ema200: bool = True
    watchlist_base_high_pct: float = 5.0
    watchlist_base_range_pct: float = 10.0
    watchlist_base_days_min: int = 10
    watchlist_atr_contraction_pct: float = -15.0
    watchlist_bbw_contraction_pct: float = -20.0
    watchlist_volume_dryup_pct: float = -25.0
    watchlist_rs_min: float = 60.0
    watchlist_sector_strength_min: float = 0.0
    
    entry_breakout_volume_ratio: float = 2.0
    entry_rs_rank_min: float = 80.0
    entry_risk_reward_min: float = 2.0
    entry_extension_pct: float = 10.0
    entry_atr_expansion_pct: float = 1.8

    ema_fast: int = 20
    ema_medium: int = 50
    ema_slow: int = 200
    
    atr_window: int = 20
    contraction_window: int = 20
    volume_sma_window: int = 20
    volume_contraction_lookback: int = 20
    volume_multiplier: float = 1.6
    relative_strength_window: int = 90
    relative_strength_period_1: int = 30
    relative_strength_period_2: int = 60
    relative_strength_period_3: int = 90
    relative_strength_min_data: int = 30
    sector_lookback: int = 60
    risk_atr_multiplier: float = 2.5

    sector_blacklist: List[str] = field(default_factory=lambda: ["Financial Services", "Utilities"])
    required_columns: List[str] = field(default_factory=lambda: ["Open", "High", "Low", "Close", "Volume"])

    def as_dict(self) -> Dict[str, object]:
        return {k: v for k, v in self.__dict__.items()}
