"""Models for the trigger engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from quality_filter.models import QualityContext
from scanner.config import ScannerConfig
from setup_engine.models import SetupResult
from transition_engine.models import TransitionResult


@dataclass(frozen=True)
class TriggerModuleResult:
    name: str
    passed: bool
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TriggerContext:
    ticker: str
    scan_mode: str
    config: ScannerConfig
    quality: QualityContext
    setup: SetupResult
    transition: TransitionResult
    frame: pd.DataFrame
    intraday_frame: Optional[pd.DataFrame] = None
    trigger_notes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TriggerResult:
    analysis_date: str
    ticker: str
    scan_mode: str
    decision: str
    confidence: str
    qualifies: bool
    trigger_score: float
    priority_score: float = 0.0
    rank_percentile: float = 100.0
    hard_gate_failures: List[str] = field(default_factory=list)
    hard_gate_passed: List[str] = field(default_factory=list)
    passed_modules: List[str] = field(default_factory=list)
    failed_modules: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    module_results: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TriggerModule:
    """Common interface for trigger modules."""

    name: str = "trigger_module"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        raise NotImplementedError
