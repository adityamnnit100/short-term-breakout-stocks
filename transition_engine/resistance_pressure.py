"""Resistance pressure gate."""

from __future__ import annotations

from typing import List

from .models import TransitionContext, TransitionGate, TransitionGateResult


class ResistancePressureGate(TransitionGate):
    name = "resistance_pressure"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        high = context.quality.high.tail(max(context.config.transition_history_window + 20, 40)).dropna()
        close = context.quality.close.tail(len(high)).dropna()
        low = context.quality.low.tail(len(high)).dropna()
        if high.empty or close.empty or low.empty:
            return TransitionGateResult(self.name, 0.0, False, weaknesses=["Missing resistance history"], metrics={"reason": "missing_history"})

        current_high = float(high.tail(20).max())
        tolerance = current_high * 0.01
        tests = int(sum(abs(float(value) - current_high) <= tolerance for value in high.tail(20).dropna().tolist()))
        acceptance_days = int(sum(float(value) >= current_high - tolerance for value in close.tail(10).dropna().tolist()))
        higher_low_sequence = bool(low.tail(5).dropna().is_monotonic_increasing)
        failed_breakdowns = int(sum(float(value) < float(low.tail(10).mean()) for value in close.tail(10).dropna().tolist()))
        time_near_highs = int(sum(abs(float(value) - current_high) <= tolerance for value in close.tail(20).dropna().tolist()))
        distance_to_high_pct = ((current_high - float(close.iloc[-1])) / current_high * 100.0) if current_high > 0 else 0.0

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if tests >= 5:
            score += 25.0
            reasons.append(f"Resistance tested {tests} times")
        elif tests >= 2:
            score += 15.0
            reasons.append(f"Resistance tested {tests} times")
        else:
            weaknesses.append("Resistance tests limited")

        if acceptance_days >= 5:
            score += 25.0
            reasons.append("Accepted near highs")
        elif acceptance_days >= 2:
            score += 15.0
        else:
            weaknesses.append("Acceptance near highs weak")

        if time_near_highs >= 5:
            score += 20.0
            reasons.append("Time spent near breakout level")
        elif time_near_highs >= 2:
            score += 10.0
        else:
            weaknesses.append("Little time near highs")

        if higher_low_sequence:
            score += 15.0
            reasons.append("Higher lows against resistance")
        else:
            weaknesses.append("Higher lows not persistent")

        if failed_breakdowns <= 1:
            score += 10.0
            reasons.append("Failed breakdowns absorbed")
        else:
            weaknesses.append("Too many failed breakdowns")

        if distance_to_high_pct <= context.config.setup_max_distance_to_high_pct:
            score += 5.0
        else:
            weaknesses.append("Too far from breakout level")

        metrics = {
            "resistance_level": round(current_high, 2),
            "resistance_tests": tests,
            "acceptance_days": acceptance_days,
            "higher_low_sequence": higher_low_sequence,
            "failed_breakdowns": failed_breakdowns,
            "time_near_highs": time_near_highs,
            "distance_to_high_pct": round(distance_to_high_pct, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return TransitionGateResult(
            self.name,
            final_score,
            final_score >= context.config.transition_min_resistance_pressure_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
