"""Volume confirmation trigger module."""

from __future__ import annotations

from typing import List

from .models import TriggerContext, TriggerModule, TriggerModuleResult


class VolumeConfirmationModule(TriggerModule):
    name = "volume_confirmation"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        volume_metrics = context.transition.metrics.get("volume_transition", {})
        rvol_5d = float(volume_metrics.get("expansion_ratio", 0.0) or 0.0)
        current_volume = float(volume_metrics.get("current_volume", 0.0) or 0.0)
        volume_transition_score = float(context.transition.volume_transition_score or 0.0)
        avg_volume = float(context.quality.avg_volume or 0.0)
        up_volume_10d = float(volume_metrics.get("up_volume_10d", 0.0) or 0.0)
        down_volume_10d = float(volume_metrics.get("down_volume_10d", 0.0) or 0.0)
        institutional_participation = up_volume_10d >= down_volume_10d
        delivery_trend_available = context.trigger_notes.get("delivery_trend", None) is not None

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []
        if volume_transition_score >= context.config.trigger_volume_transition_min:
            score += 45.0
            reasons.append("Volume transition confirms participation")
        else:
            weaknesses.append("Volume transition weak")
        if rvol_5d >= context.config.trigger_breakout_volume_ratio_min:
            score += 25.0
            reasons.append("Volume spike quality strong")
        else:
            weaknesses.append("Relative volume spike weak")
        if institutional_participation:
            score += 20.0
            reasons.append("Up-volume leading down-volume")
        else:
            weaknesses.append("Institutional participation not evident")
        if avg_volume > 0 and current_volume >= avg_volume:
            score += 10.0
            reasons.append("Current volume above average")

        metrics = {
            "current_volume": round(current_volume, 2),
            "rvol_5d": round(rvol_5d, 2),
            "volume_transition_score": round(volume_transition_score, 2),
            "institutional_participation": institutional_participation,
            "delivery_trend_available": delivery_trend_available,
        }
        final_score = round(min(score, 100.0), 2)
        return TriggerModuleResult(
            self.name,
            passed=volume_transition_score >= context.config.trigger_volume_transition_min and rvol_5d >= context.config.trigger_breakout_volume_ratio_min and institutional_participation,
            score=final_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
