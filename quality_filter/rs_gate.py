"""Relative-strength qualification gate."""

from __future__ import annotations

from .models import GateResult, QualityContext, QualityGate


class RSGate(QualityGate):
    name = "relative_strength"

    def evaluate(self, context: QualityContext) -> GateResult:
        min_rs = float(context.config.quality_min_relative_strength) * context.market_threshold_multiplier
        if context.relative_strength < min_rs:
            return GateResult(
                name=self.name,
                passed=False,
                reason="Relative Strength Below Threshold",
                detail={"relative_strength": round(float(context.relative_strength), 2), "min_relative_strength": round(min_rs, 2)},
            )
        return GateResult(
            name=self.name,
            passed=True,
            detail={"relative_strength": round(float(context.relative_strength), 2), "min_relative_strength": round(min_rs, 2)},
        )
