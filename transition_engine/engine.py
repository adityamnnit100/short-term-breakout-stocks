"""Transition engine orchestrator."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Iterable, List, Optional

import pandas as pd

from quality_filter.models import QualityContext
from scanner.config import ScannerConfig
from setup_engine.models import SetupResult

from .compression_evolution import CompressionEvolutionGate
from .models import TransitionContext, TransitionGate, TransitionGateResult, TransitionHistoryPoint, TransitionResult
from .opportunity_velocity import OpportunityVelocityGate
from .price_acceptance import PriceAcceptanceGate
from .resistance_pressure import ResistancePressureGate
from .rs_acceleration import RSAccelerationGate
from .setup_velocity import SetupVelocityGate
from .volume_transition import VolumeTransitionGate

logger = logging.getLogger("AlphaScanner.Transition")

HistoryLoader = Callable[[str, str, int], Iterable[dict]]


def _default_history_loader(ticker: str, scan_mode: str, limit: int) -> List[dict]:
    try:
        from alphascanner_ui.database import execute_query
    except Exception:
        return []

    rows = execute_query(
        """
        SELECT analysis_date, scan_mode, setup_score
        FROM setup_analyses
        WHERE ticker = ? AND scan_mode = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (ticker, scan_mode, limit),
        is_select=True,
    )
    return [dict(row) for row in reversed(rows)] if rows else []


class TransitionEngine:
    """Measure whether a setup is moving from accumulation into expansion."""

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        gates: Optional[Iterable[TransitionGate]] = None,
        history_loader: Optional[HistoryLoader] = None,
    ):
        self.config = config or ScannerConfig()
        self.history_loader = history_loader or _default_history_loader
        self.gates: List[TransitionGate] = list(gates) if gates is not None else [
            SetupVelocityGate(),
            RSAccelerationGate(),
            VolumeTransitionGate(),
            CompressionEvolutionGate(),
            ResistancePressureGate(),
            PriceAcceptanceGate(),
            OpportunityVelocityGate(),
        ]

    def build_context(
        self,
        quality_context: QualityContext,
        setup_result: SetupResult,
        scan_mode: str = "Watchlist",
    ) -> TransitionContext:
        history_rows = []
        if self.history_loader is not None:
            try:
                history_rows = list(self.history_loader(quality_context.ticker, scan_mode, self.config.transition_history_window))
            except Exception as exc:
                logger.warning("Transition history lookup failed for %s: %s", quality_context.ticker, exc)
                history_rows = []

        history = [TransitionHistoryPoint.from_mapping(row) for row in history_rows]
        return TransitionContext(
            ticker=quality_context.ticker,
            scan_mode=scan_mode,
            config=self.config,
            quality=quality_context,
            setup=setup_result,
            frame=quality_context.frame,
            history=history,
        )

    def evaluate(self, context: TransitionContext) -> TransitionResult:
        if not self.config.transition_engine_enabled:
            return TransitionResult(
                analysis_date=datetime.now().strftime("%Y-%m-%d"),
                ticker=context.ticker,
                scan_mode=context.scan_mode,
                transition_score=0.0,
                setup_velocity_score=0.0,
                rs_acceleration_score=0.0,
                volume_transition_score=0.0,
                compression_evolution_score=0.0,
                resistance_pressure_score=0.0,
                price_acceptance_score=0.0,
                opportunity_velocity_score=0.0,
                category="Disabled",
                qualifies=False,
                reasons=["Transition engine disabled"],
                weaknesses=[],
                metrics={"transition_engine": "disabled"},
            )

        gate_results: List[TransitionGateResult] = []
        gate_map = {}
        reasons: List[str] = []
        weaknesses: List[str] = []

        for gate in self.gates:
            result = gate.evaluate(context)
            gate_results.append(result)
            gate_map[gate.name] = result
            context.transition_notes[f"{gate.name}_score"] = result.score
            context.transition_notes[gate.name] = result.metrics
            reasons.extend(result.reasons)
            weaknesses.extend(result.weaknesses)

        setup_velocity_score = gate_map["setup_velocity"].score if "setup_velocity" in gate_map else 0.0
        rs_acceleration_score = gate_map["rs_acceleration"].score if "rs_acceleration" in gate_map else 0.0
        volume_transition_score = gate_map["volume_transition"].score if "volume_transition" in gate_map else 0.0
        compression_evolution_score = gate_map["compression_evolution"].score if "compression_evolution" in gate_map else 0.0
        resistance_pressure_score = gate_map["resistance_pressure"].score if "resistance_pressure" in gate_map else 0.0
        price_acceptance_score = gate_map["price_acceptance"].score if "price_acceptance" in gate_map else 0.0
        opportunity_velocity_score = gate_map["opportunity_velocity"].score if "opportunity_velocity" in gate_map else 0.0

        transition_score = round(
            min(
                setup_velocity_score * self.config.transition_weight_setup_velocity
                + rs_acceleration_score * self.config.transition_weight_rs_acceleration
                + volume_transition_score * self.config.transition_weight_volume_transition
                + compression_evolution_score * self.config.transition_weight_compression_evolution
                + resistance_pressure_score * self.config.transition_weight_resistance_pressure
                + price_acceptance_score * self.config.transition_weight_price_acceptance
                + opportunity_velocity_score * self.config.transition_weight_opportunity_velocity,
                100.0,
            ),
            2,
        )

        if transition_score >= self.config.transition_professional_threshold:
            category = "Professional"
        elif transition_score >= self.config.transition_strong_threshold:
            category = "Strong"
        elif transition_score >= self.config.transition_building_threshold:
            category = "Building"
        elif transition_score >= self.config.transition_watch_threshold:
            category = "Watch"
        else:
            category = "Weak"

        qualifies = transition_score >= self.config.transition_watch_threshold and all(result.passed for result in gate_results)
        metrics = {result.name: result.metrics for result in gate_results}

        return TransitionResult(
            analysis_date=datetime.now().strftime("%Y-%m-%d"),
            ticker=context.ticker,
            scan_mode=context.scan_mode,
            transition_score=transition_score,
            setup_velocity_score=setup_velocity_score,
            rs_acceleration_score=rs_acceleration_score,
            volume_transition_score=volume_transition_score,
            compression_evolution_score=compression_evolution_score,
            resistance_pressure_score=resistance_pressure_score,
            price_acceptance_score=price_acceptance_score,
            opportunity_velocity_score=opportunity_velocity_score,
            category=category,
            qualifies=qualifies,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
            gate_results={
                result.name: {
                    "passed": result.passed,
                    "score": result.score,
                    "reasons": list(result.reasons),
                    "weaknesses": list(result.weaknesses),
                    "metrics": dict(result.metrics),
                }
                for result in gate_results
            },
        )
