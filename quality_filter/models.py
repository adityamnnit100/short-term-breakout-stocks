"""Models for the quality filter engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from scanner.config import ScannerConfig


@dataclass(frozen=True)
class QualityResult:
    passed: bool
    rejection_reason: str
    failed_checks: List[str] = field(default_factory=list)
    passed_checks: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    gate_results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityContext:
    ticker: str
    sector: str
    config: ScannerConfig
    frame: pd.DataFrame
    close: pd.Series
    high: pd.Series
    low: pd.Series
    open: pd.Series
    volume: pd.Series
    ema20: pd.Series
    ema50: pd.Series
    ema200: pd.Series
    atr: pd.Series
    latest_close: float
    latest_ema20: float
    latest_ema50: float
    latest_ema200: float
    latest_atr: float
    avg_volume: float
    current_volume: float
    avg_turnover: float
    recent_high_20d: float
    recent_high_40d: float
    recent_low_20d: float
    days_in_consolidation: int
    higher_highs: bool
    higher_lows: bool
    trend_template_pass: bool
    relative_strength: float
    sector_strength: float = 0.0
    market_regime: str = "UNKNOWN"
    market_regime_score: float = 0.0
    market_threshold_multiplier: float = 1.0
    market_cap_cr: float = 0.0
    market_cap_mode: str = "Custom"
    market_cap_custom_symbols: Optional[List[str]] = None
    quality_notes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    reason: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)


class QualityGate:
    """Common interface for all quality gates."""

    name: str = "gate"

    def evaluate(self, context: QualityContext) -> GateResult:
        raise NotImplementedError
