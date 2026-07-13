"""Sector qualification gate."""

from __future__ import annotations

from .models import GateResult, QualityContext, QualityGate


class SectorGate(QualityGate):
    name = "sector"

    def evaluate(self, context: QualityContext) -> GateResult:
        min_sector = float(context.config.quality_min_sector_strength) * context.market_threshold_multiplier
        if context.sector_strength < min_sector:
            return GateResult(
                name=self.name,
                passed=False,
                reason="Weak Sector",
                detail={"sector_strength": round(float(context.sector_strength), 2), "min_sector_strength": round(min_sector, 2)},
            )
        return GateResult(
            name=self.name,
            passed=True,
            detail={"sector_strength": round(float(context.sector_strength), 2), "min_sector_strength": round(min_sector, 2)},
        )
