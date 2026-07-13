"""Setup engine orchestrator."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, List, Optional

from quality_filter.models import QualityContext
from scanner.config import ScannerConfig

from .base_quality import BaseQualityGate
from .compression import CompressionGate
from .models import SetupGate, SetupGateResult, SetupResult
from .resistance import ResistanceGate
from .risk import RiskGate
from .structure import StructureGate
from .volume_dryup import VolumeDryupGate

logger = logging.getLogger("AlphaScanner.Setup")


class SetupEngine:
    """Structural setup engine for professional-quality launchpads."""

    def __init__(self, config: Optional[ScannerConfig] = None, gates: Optional[Iterable[SetupGate]] = None):
        self.config = config or ScannerConfig()
        self.gates: List[SetupGate] = list(gates) if gates is not None else [
            BaseQualityGate("base_quality"),
            CompressionGate("compression"),
            VolumeDryupGate("volume_dryup"),
            ResistanceGate("resistance"),
            StructureGate("structure"),
            RiskGate("risk"),
        ]

    def evaluate(self, context: QualityContext) -> SetupResult:
        if not self.config.setup_engine_enabled:
            return SetupResult(
                analysis_date=datetime.now().strftime("%Y-%m-%d"),
                ticker=context.ticker,
                setup_score=0.0,
                base_score=0.0,
                compression_score=0.0,
                volume_score=0.0,
                resistance_score=0.0,
                structure_score=0.0,
                risk_score=0.0,
                category="Poor",
                qualifies=False,
                reasons=["Setup engine disabled"],
                weaknesses=[],
                metrics={"setup_engine": "disabled"},
            )

        gate_results: List[SetupGateResult] = []
        gate_map = {}
        reasons: List[str] = []
        weaknesses: List[str] = []

        for gate in self.gates:
            result = gate.evaluate(context)
            gate_results.append(result)
            gate_map[gate.name] = result
            reasons.extend(result.reasons)
            weaknesses.extend(result.weaknesses)

        base_score = gate_map["base_quality"].score if "base_quality" in gate_map else 0.0
        compression_score = gate_map["compression"].score if "compression" in gate_map else 0.0
        volume_score = gate_map["volume_dryup"].score if "volume_dryup" in gate_map else 0.0
        resistance_score = gate_map["resistance"].score if "resistance" in gate_map else 0.0
        structure_score = gate_map["structure"].score if "structure" in gate_map else 0.0
        risk_score = gate_map["risk"].score if "risk" in gate_map else 0.0

        setup_score = round(
            min(
                base_score * self.config.setup_weight_base
                + compression_score * self.config.setup_weight_compression
                + volume_score * self.config.setup_weight_volume
                + resistance_score * self.config.setup_weight_resistance
                + structure_score * self.config.setup_weight_structure
                + risk_score * self.config.setup_weight_risk,
                100.0,
            ),
            2,
        )

        if setup_score >= self.config.setup_professional_threshold:
            category = "Professional"
        elif setup_score >= self.config.setup_excellent_threshold:
            category = "Excellent"
        elif setup_score >= self.config.setup_good_threshold:
            category = "Good"
        elif setup_score >= self.config.setup_average_threshold:
            category = "Average"
        else:
            category = "Poor"

        qualifies = setup_score >= self.config.setup_average_threshold and all(result.passed for result in gate_results)
        context.quality_notes["setup_score"] = setup_score
        context.quality_notes["setup_category"] = category
        context.quality_notes["setup_reasons"] = reasons
        context.quality_notes["setup_weaknesses"] = weaknesses
        context.quality_notes["setup_metrics"] = {result.name: result.metrics for result in gate_results}

        return SetupResult(
            analysis_date=datetime.now().strftime("%Y-%m-%d"),
            ticker=context.ticker,
            setup_score=setup_score,
            base_score=base_score,
            compression_score=compression_score,
            volume_score=volume_score,
            resistance_score=resistance_score,
            structure_score=structure_score,
            risk_score=risk_score,
            category=category,
            qualifies=qualifies,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics={result.name: result.metrics for result in gate_results},
        )
