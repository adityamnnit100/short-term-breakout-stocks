"""Opportunity velocity gate."""

from __future__ import annotations

from typing import List

from .models import TransitionContext, TransitionGate, TransitionGateResult


class OpportunityVelocityGate(TransitionGate):
    name = "opportunity_velocity"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        setup_velocity = float(context.transition_notes.get("setup_velocity_score", 0.0) or 0.0)
        rs_acceleration = float(context.transition_notes.get("rs_acceleration_score", 0.0) or 0.0)
        volume_transition = float(context.transition_notes.get("volume_transition_score", 0.0) or 0.0)
        compression_evolution = float(context.transition_notes.get("compression_evolution_score", 0.0) or 0.0)

        score = (
            setup_velocity * 0.30
            + rs_acceleration * 0.25
            + volume_transition * 0.25
            + compression_evolution * 0.20
        )

        reasons: List[str] = []
        weaknesses: List[str] = []

        if setup_velocity >= 70:
            reasons.append("Setup velocity strong")
        elif setup_velocity < 45:
            weaknesses.append("Setup velocity lagging")

        if rs_acceleration >= 70:
            reasons.append("RS acceleration strong")
        elif rs_acceleration < 45:
            weaknesses.append("RS acceleration lagging")

        if volume_transition >= 70:
            reasons.append("Volume transition strong")
        elif volume_transition < 45:
            weaknesses.append("Volume transition lagging")

        if compression_evolution >= 70:
            reasons.append("Compression evolution strong")
        elif compression_evolution < 45:
            weaknesses.append("Compression evolution lagging")

        if score >= 75:
            reasons.append("Opportunity velocity compelling")
        elif score < 50:
            weaknesses.append("Opportunity velocity weak")

        metrics = {
            "setup_velocity_score": round(setup_velocity, 2),
            "rs_acceleration_score": round(rs_acceleration, 2),
            "volume_transition_score": round(volume_transition, 2),
            "compression_evolution_score": round(compression_evolution, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return TransitionGateResult(
            self.name,
            final_score,
            final_score >= context.config.transition_min_opportunity_velocity_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
