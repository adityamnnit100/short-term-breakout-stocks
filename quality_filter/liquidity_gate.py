"""Liquidity gate for the quality filter."""

from __future__ import annotations

from .models import GateResult, QualityContext, QualityGate


class LiquidityGate(QualityGate):
    name = "liquidity"

    def evaluate(self, context: QualityContext) -> GateResult:
        min_volume = float(context.config.quality_min_avg_volume) * context.market_threshold_multiplier
        min_turnover = float(context.config.quality_min_avg_turnover) * context.market_threshold_multiplier

        if context.avg_volume < min_volume:
            return GateResult(
                name=self.name,
                passed=False,
                reason="Liquidity Too Low",
                detail={"avg_volume": round(float(context.avg_volume), 2), "min_avg_volume": round(min_volume, 2)},
            )
        if context.avg_turnover < min_turnover:
            return GateResult(
                name=self.name,
                passed=False,
                reason="Average Daily Turnover Too Low",
                detail={"avg_turnover": round(float(context.avg_turnover), 2), "min_avg_turnover": round(min_turnover, 2)},
            )
        return GateResult(
            name=self.name,
            passed=True,
            detail={"avg_volume": round(float(context.avg_volume), 2), "avg_turnover": round(float(context.avg_turnover), 2)},
        )
