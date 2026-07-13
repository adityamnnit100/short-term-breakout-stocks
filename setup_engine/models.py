"""Models for the setup engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from quality_filter.models import QualityContext


@dataclass(frozen=True)
class SetupGateResult:
    name: str
    score: float
    passed: bool
    reasons: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SetupResult:
    analysis_date: str
    ticker: str
    setup_score: float
    base_score: float
    compression_score: float
    volume_score: float
    resistance_score: float
    structure_score: float
    risk_score: float
    category: str
    qualifies: bool
    reasons: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SetupGate:
    name: str

    def evaluate(self, context: QualityContext) -> SetupGateResult:
        raise NotImplementedError
