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
    scan_max_workers: int = 8
    scan_download_chunk_size: int = 25
    diagnostics_enabled: bool = False
    diagnostics_persist: bool = True
    diagnostics_top_rules: int = 3

    # Watchlist score composition
    watchlist_setup_weight: float = 0.60
    watchlist_transition_weight: float = 0.40

    # Entry score composition
    entry_setup_weight: float = 0.30
    entry_transition_weight: float = 0.30
    entry_trigger_weight: float = 0.40

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

    quality_filter_enabled: bool = True
    quality_min_avg_volume: float = 0.0
    quality_min_avg_turnover: float = 0.0
    quality_min_market_cap_cr: float = 0.0
    quality_max_market_cap_cr: float = 0.0
    quality_market_cap_mode: str = "Custom"
    quality_market_cap_custom_symbols: List[str] = field(default_factory=list)
    quality_min_relative_strength: float = 0.0
    quality_min_sector_strength: float = 0.0
    quality_require_price_above_ema200: bool = False
    quality_require_ema_alignment: bool = False
    quality_require_trend_template: bool = False
    quality_require_higher_highs: bool = False
    quality_require_higher_lows: bool = False
    quality_market_bearish_multiplier: float = 1.25
    quality_market_bullish_multiplier: float = 1.0
    quality_market_neutral_multiplier: float = 1.0
    quality_market_caution_multiplier: float = 1.1

    setup_engine_enabled: bool = True
    setup_min_base_quality_score: float = 60.0
    setup_min_base_weeks: int = 8
    setup_max_base_depth_pct: float = 18.0
    setup_max_base_duration_weeks: int = 24
    setup_max_distance_to_high_pct: float = 8.0
    setup_volume_long_window: int = 50
    setup_volume_short_window: int = 20
    setup_min_compression_score: float = 40.0
    setup_min_volume_score: float = 35.0
    setup_min_resistance_score: float = 35.0
    setup_min_structure_score: float = 40.0
    setup_min_risk_score: float = 35.0
    setup_weight_base: float = 0.20
    setup_weight_compression: float = 0.20
    setup_weight_volume: float = 0.15
    setup_weight_resistance: float = 0.20
    setup_weight_structure: float = 0.15
    setup_weight_risk: float = 0.10
    setup_professional_threshold: float = 90.0
    setup_excellent_threshold: float = 80.0
    setup_good_threshold: float = 70.0
    setup_average_threshold: float = 55.0

    transition_engine_enabled: bool = True
    transition_history_window: int = 10
    transition_min_setup_velocity_score: float = 55.0
    transition_min_rs_acceleration_score: float = 55.0
    transition_min_volume_transition_score: float = 55.0
    transition_min_compression_evolution_score: float = 55.0
    transition_min_resistance_pressure_score: float = 50.0
    transition_min_price_acceptance_score: float = 50.0
    transition_min_opportunity_velocity_score: float = 60.0
    transition_weight_setup_velocity: float = 0.18
    transition_weight_rs_acceleration: float = 0.14
    transition_weight_volume_transition: float = 0.18
    transition_weight_compression_evolution: float = 0.14
    transition_weight_resistance_pressure: float = 0.12
    transition_weight_price_acceptance: float = 0.10
    transition_weight_opportunity_velocity: float = 0.14
    transition_professional_threshold: float = 90.0
    transition_strong_threshold: float = 80.0
    transition_building_threshold: float = 70.0
    transition_watch_threshold: float = 55.0

    trigger_engine_enabled: bool = True
    trigger_enable_pocket_pivot: bool = True
    trigger_enable_relative_volume: bool = True
    trigger_enable_breakout_confirmation: bool = True
    trigger_enable_closing_strength: bool = True
    trigger_enable_rs_confirmation: bool = True
    trigger_enable_volume_confirmation: bool = True
    trigger_enable_intraday_confirmation: bool = False
    trigger_min_setup_score: float = 80.0
    trigger_min_transition_score: float = 80.0
    trigger_min_trigger_score: float = 75.0
    trigger_pocket_pivot_volume_ratio: float = 1.5
    trigger_pocket_pivot_close_location_min: float = 0.7
    trigger_relative_volume_5d_min: float = 1.2
    trigger_relative_volume_10d_min: float = 1.1
    trigger_relative_volume_20d_min: float = 1.0
    trigger_breakout_buffer_pct: float = 0.25
    trigger_breakout_volume_ratio_min: float = 1.8
    trigger_close_location_min: float = 0.8
    trigger_close_strength_min: float = 0.75
    trigger_rs_proxy_min: float = 105.0
    trigger_rs_transition_min: float = 55.0
    trigger_volume_transition_min: float = 60.0
    trigger_intraday_vwap_hold_min: float = 0.0
    trigger_intraday_rvol_min: float = 1.2
    trigger_intraday_high_hold_min: float = 0.95
    trigger_buy_now_top_percentile: float = 2.0
    trigger_early_buy_top_percentile: float = 5.0
    trigger_watch_top_percentile: float = 10.0
    trigger_early_buy_soft_miss_max: int = 1
    trigger_calibration_mode: bool = False

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
