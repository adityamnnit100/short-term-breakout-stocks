"""Data models for market regime scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class MarketRegimeResult:
    score: float
    regime: str
    score_multiplier: float
    buy_min_score: float
    reasons: List[str] = field(default_factory=list)
    components: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
