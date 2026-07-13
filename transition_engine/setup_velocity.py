"""Setup-score velocity gate."""

from __future__ import annotations

from typing import List

import numpy as np

from .models import TransitionContext, TransitionGate, TransitionGateResult


def _slope(values: List[float]) -> float:
    clean = [float(value) for value in values if value is not None]
    if len(clean) < 2:
        return 0.0
    x = np.arange(len(clean), dtype=float)
    y = np.asarray(clean, dtype=float)
    try:
        return float(np.polyfit(x, y, 1)[0])
    except Exception:
        return 0.0


class SetupVelocityGate(TransitionGate):
    name = "setup_velocity"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        history = [point.setup_score for point in context.history if point.scan_mode == context.scan_mode or not point.scan_mode]
        history = [float(value) for value in history if value is not None]

        current = float(context.setup.setup_score or 0.0)
        if not history:
            base_score = min(current, 100.0) * 0.35
            return TransitionGateResult(
                self.name,
                round(base_score, 2),
                base_score >= context.config.transition_min_setup_velocity_score,
                reasons=["Setup history unavailable"],
                weaknesses=["Insufficient historical setup data"],
                metrics={
                    "current_setup_score": round(current, 2),
                    "daily_delta": 0.0,
                    "slope_3d": 0.0,
                    "slope_5d": 0.0,
                    "moving_average_improvement": 0.0,
                },
            )

        recent = history[-10:]
        last_1 = recent[-1] if len(recent) >= 1 else current
        last_3 = sum(recent[-3:]) / min(len(recent), 3)
        last_5 = sum(recent[-5:]) / min(len(recent), 5)
        last_10 = sum(recent[-10:]) / min(len(recent), 10)

        daily_delta = current - last_1
        slope_3d = current - last_3
        slope_5d = current - last_5
        slope_10d = current - last_10
        improvement_values = [current - value for value in recent[-5:]]
        moving_average_improvement = sum(improvement_values) / len(improvement_values) if improvement_values else 0.0
        trend_slope = _slope(recent + [current])

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if daily_delta >= 5:
            score += 25.0
            reasons.append("Setup score jumped sharply day-over-day")
        elif daily_delta >= 2:
            score += 18.0
            reasons.append("Setup score improving daily")
        elif daily_delta >= 0.5:
            score += 10.0
        elif daily_delta < -1:
            weaknesses.append("Setup score stalled")

        if slope_3d >= 4:
            score += 20.0
            reasons.append("Strong 3-day setup slope")
        elif slope_3d >= 1.5:
            score += 12.0
        elif slope_3d < 0:
            weaknesses.append("3-day setup slope negative")

        if slope_5d >= 4:
            score += 20.0
            reasons.append("Strong 5-day setup slope")
        elif slope_5d >= 1.5:
            score += 12.0
        elif slope_5d < 0:
            weaknesses.append("5-day setup slope negative")

        if moving_average_improvement >= 2:
            score += 15.0
            reasons.append("Improvement average rising")
        elif moving_average_improvement >= 0.5:
            score += 8.0
        else:
            weaknesses.append("Improvement average weak")

        if slope_10d >= 5 or trend_slope >= 1.0:
            score += 20.0
            reasons.append("Setup accelerating over 10 sessions")
        elif slope_10d >= 2:
            score += 10.0
        else:
            weaknesses.append("10-day setup trend muted")

        score += min(max(current / 100.0, 0.0), 1.0) * 10.0

        metrics = {
            "current_setup_score": round(current, 2),
            "daily_delta": round(daily_delta, 2),
            "slope_3d": round(slope_3d, 2),
            "slope_5d": round(slope_5d, 2),
            "slope_10d": round(slope_10d, 2),
            "moving_average_improvement": round(moving_average_improvement, 2),
            "trend_slope": round(trend_slope, 4),
            "history_points": len(history),
        }
        final_score = round(min(score, 100.0), 2)
        return TransitionGateResult(
            self.name,
            final_score,
            final_score >= context.config.transition_min_setup_velocity_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
