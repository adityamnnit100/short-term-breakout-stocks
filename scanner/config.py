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

    market_regime_trend_weight: float = 0.30
    market_regime_breadth_weight: float = 0.25
    market_regime_momentum_weight: float = 0.20
    market_regime_volume_weight: float = 0.15
    market_regime_volatility_weight: float = 0.10
    market_regime_bullish_threshold: float = 75.0
    market_regime_neutral_threshold: float = 55.0
    market_regime_caution_threshold: float = 40.0
    market_regime_bearish_threshold: float = 0.0
    market_regime_bullish_penalty: float = 1.00
    market_regime_neutral_penalty: float = 0.95
    market_regime_caution_penalty: float = 0.85
    market_regime_bearish_penalty: float = 0.70
    market_regime_buy_min_bullish: float = 80.0
    market_regime_buy_min_neutral: float = 85.0
    market_regime_buy_min_caution: float = 90.0
    market_regime_buy_min_bearish: float = 95.0
    market_regime_nifty50_period: str = "2y"
    market_regime_nifty500_period: str = "2y"
    market_regime_breadth_min_above_ema20: float = 45.0
    market_regime_breadth_min_above_ema50: float = 40.0
    market_regime_breadth_min_above_ema200: float = 25.0
    market_regime_atr_window: int = 14
    market_regime_volume_window: int = 20
    market_regime_volatility_window: int = 20
    market_regime_momentum_return_cap_pct: float = 10.0
    market_regime_ema_buffer_pct: float = 0.5
    market_regime_distribution_day_window: int = 20
    market_regime_accumulation_day_window: int = 20
    market_regime_volume_trend_threshold_pct: float = 10.0
    market_regime_volatility_high_threshold_pct: float = 15.0
    market_regime_volatility_mid_threshold_pct: float = 8.0
    market_regime_accumulation_edge_days: int = 2
    market_regime_distribution_edge_days: int = 2

    mtf_weekly_weight: float = 20.0
    mtf_daily_weight: float = 50.0
    mtf_hourly_weight: float = 30.0
    mtf_weekly_max_points: float = 20.0
    mtf_daily_max_points: float = 50.0
    mtf_hourly_max_points: float = 30.0
    mtf_strong_buy_threshold: float = 90.0
    mtf_buy_threshold: float = 80.0
    mtf_watch_threshold: float = 65.0
    mtf_wait_threshold: float = 50.0
    mtf_weekly_bullish_threshold: float = 14.0
    mtf_weekly_neutral_threshold: float = 10.0
    mtf_weekly_bearish_threshold: float = 6.0
    mtf_daily_bullish_threshold: float = 35.0
    mtf_daily_neutral_threshold: float = 25.0
    mtf_hourly_bullish_threshold: float = 20.0
    mtf_hourly_neutral_threshold: float = 12.0
    mtf_weekly_lookback_period: str = "2y"
    mtf_daily_lookback_period: str = "1y"
    mtf_hourly_lookback_period: str = "60d"
    mtf_hourly_ema_fast: int = 20
    mtf_hourly_ema_slow: int = 50
    mtf_weekly_veto_enabled: bool = True
    mtf_enable_confirmation: bool = False

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
