"""Resistance structure setup gate."""

from __future__ import annotations

from typing import List

import pandas as pd

from quality_filter.models import QualityContext
from .models import SetupGate, SetupGateResult


class ResistanceGate(SetupGate):
    name = "resistance"

    def evaluate(self, context: QualityContext) -> SetupGateResult:
        cfg = context.config
        high = context.high.tail(60).dropna()
        close = context.close.tail(60).dropna()
        if high.empty or close.empty:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Missing resistance history"], metrics={"reason": "missing_history"})

        resistance = float(high.tail(20).max())
        tolerance = resistance * 0.0125
        tests = int(sum(abs(float(v) - resistance) <= tolerance for v in high.tail(40).dropna().tolist()))
        distance_to_high_pct = ((resistance - float(close.iloc[-1])) / resistance * 100.0) if resistance > 0 else 0.0
        time_near_resistance = int(sum(abs(float(v) - resistance) <= tolerance for v in close.tail(20).dropna().tolist()))
        tightness_near_highs = 1.0 - min((float(high.tail(10).max()) - float(high.tail(10).min())) / max(resistance, 1e-9), 1.0)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if tests >= 6:
            score += 35.0
            reasons.append(f"Resistance tested {tests} times")
        elif tests >= 3:
            score += 25.0
            reasons.append(f"Repeated resistance tests ({tests})")
        elif tests >= 1:
            score += 15.0
        else:
            weaknesses.append("Resistance not established")

        if distance_to_high_pct <= cfg.setup_max_distance_to_high_pct:
            score += 25.0
            reasons.append("Close to breakout level")
        elif distance_to_high_pct <= cfg.setup_max_distance_to_high_pct * 1.5:
            score += 12.0
        else:
            weaknesses.append("Too far from highs")

        if time_near_resistance >= 5:
            score += 20.0
            reasons.append("Time spent near resistance")
        elif time_near_resistance >= 2:
            score += 10.0

        if tightness_near_highs >= 0.7:
            score += 20.0
            reasons.append("Tight near highs")
        elif tightness_near_highs >= 0.5:
            score += 10.0
        else:
            weaknesses.append("Not tight near highs")

        metrics = {
            "resistance": round(resistance, 2),
            "resistance_tests": tests,
            "distance_to_high_pct": round(distance_to_high_pct, 2),
            "time_near_resistance": time_near_resistance,
            "tightness_near_highs": round(tightness_near_highs, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return SetupGateResult(self.name, final_score, final_score >= cfg.setup_min_resistance_score, reasons=reasons, weaknesses=weaknesses, metrics=metrics)
