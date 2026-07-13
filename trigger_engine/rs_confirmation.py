"""Relative strength confirmation trigger module."""

from __future__ import annotations

from typing import List

from .models import TriggerContext, TriggerModule, TriggerModuleResult


class RSConfirmationModule(TriggerModule):
    name = "rs_confirmation"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        rs_metrics = context.transition.metrics.get("rs_acceleration", {})
        current_rs_proxy = float(rs_metrics.get("current_rs_proxy", 0.0) or 0.0)
        rs_new_high = bool(rs_metrics.get("new_high", False))
        rs_leadership = bool(rs_metrics.get("leadership", False))
        rs_transition_score = float(context.transition.rs_acceleration_score or 0.0)
        quality_rs = float(context.quality.relative_strength or 0.0)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []
        if current_rs_proxy >= context.config.trigger_rs_proxy_min:
            score += 40.0
            reasons.append("RS making a new high")
        else:
            weaknesses.append("RS proxy not at new highs")
        if rs_transition_score >= context.config.trigger_rs_transition_min:
            score += 35.0
            reasons.append("RS acceleration confirmed")
        else:
            weaknesses.append("RS acceleration weak")
        if rs_leadership:
            score += 15.0
            reasons.append("RS leading price")
        else:
            weaknesses.append("RS leadership not confirmed")
        if quality_rs >= 50.0:
            score += 10.0
            reasons.append("Outperforming market context")
        else:
            weaknesses.append("RS vs market weak")

        metrics = {
            "current_rs_proxy": round(current_rs_proxy, 2),
            "rs_new_high": rs_new_high,
            "rs_leadership": rs_leadership,
            "rs_transition_score": round(rs_transition_score, 2),
            "quality_relative_strength": round(quality_rs, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return TriggerModuleResult(
            self.name,
            passed=current_rs_proxy >= context.config.trigger_rs_proxy_min and rs_transition_score >= context.config.trigger_rs_transition_min and rs_leadership,
            score=final_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
