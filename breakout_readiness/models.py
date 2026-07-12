"""Data models for the Breakout Readiness Engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ScanResult:
    ticker: str
    current_price: float = 0.0
    sector: str = "Unknown"
    scanner_type: Optional[str] = None
    universe: Optional[str] = None
    source_row: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BreakoutReadyResult:
    ticker: str
    breakout_readiness_score: float
    current_price: float
    nearest_resistance: float
    resistance_gap_pct: float
    compression_score: float
    breakout_distance_score: float
    volume_dryup_score: float
    candle_tightness_score: float
    rs_acceleration_score: float
    breakout_pressure_score: float
    confluence_bonus: float
    sector: str = "Unknown"
    reasons: tuple = ()
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
