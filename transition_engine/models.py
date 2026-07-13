"""Models for the transition engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from quality_filter.models import QualityContext
from scanner.config import ScannerConfig
from setup_engine.models import SetupResult


@dataclass(frozen=True)
class TransitionHistoryPoint:
    analysis_date: str
    scan_mode: str
    setup_score: float = 0.0
    transition_score: float = 0.0

    @classmethod
    def from_mapping(cls, data: Dict[str, Any]) -> "TransitionHistoryPoint":
        return cls(
            analysis_date=str(data.get("analysis_date", "") or ""),
            scan_mode=str(data.get("scan_mode", "") or ""),
            setup_score=float(data.get("setup_score", 0.0) or 0.0),
            transition_score=float(data.get("transition_score", 0.0) or 0.0),
        )


@dataclass
class TransitionContext:
    ticker: str
    scan_mode: str
    config: ScannerConfig
    quality: QualityContext
    setup: SetupResult
    frame: pd.DataFrame
    history: List[TransitionHistoryPoint] = field(default_factory=list)
    transition_notes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransitionGateResult:
    name: str
    score: float
    passed: bool
    reasons: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransitionResult:
    analysis_date: str
    ticker: str
    scan_mode: str
    transition_score: float
    setup_velocity_score: float
    rs_acceleration_score: float
    volume_transition_score: float
    compression_evolution_score: float
    resistance_pressure_score: float
    price_acceptance_score: float
    opportunity_velocity_score: float
    category: str
    qualifies: bool
    reasons: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    gate_results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TransitionGate:
    """Common interface for all transition gates."""

    name: str = "transition_gate"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        raise NotImplementedError
