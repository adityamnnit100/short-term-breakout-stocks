"""Market regime qualification gate."""

from __future__ import annotations

from .models import GateResult, QualityContext, QualityGate


class MarketGate(QualityGate):
    name = "market"

    def evaluate(self, context: QualityContext) -> GateResult:
        regime = str(context.market_regime or "UNKNOWN").upper()
        if regime == "BEARISH":
            context.market_threshold_multiplier = max(float(context.config.quality_market_bearish_multiplier), 1.0)
            return GateResult(
                name=self.name,
                passed=True,
                reason="Market Bearish - Threshold Tightened",
                detail={"market_regime": regime, "threshold_multiplier": round(float(context.market_threshold_multiplier), 2)},
            )
        if regime == "CAUTION":
            context.market_threshold_multiplier = max(float(context.config.quality_market_caution_multiplier), 1.0)
            return GateResult(
                name=self.name,
                passed=True,
                reason="Market Caution - Threshold Tightened",
                detail={"market_regime": regime, "threshold_multiplier": round(float(context.market_threshold_multiplier), 2)},
            )
        if regime == "BULLISH":
            context.market_threshold_multiplier = max(float(context.config.quality_market_bullish_multiplier), 1.0)
        else:
            context.market_threshold_multiplier = max(float(context.config.quality_market_neutral_multiplier), 1.0)
        return GateResult(
            name=self.name,
            passed=True,
            detail={"market_regime": regime, "threshold_multiplier": round(float(context.market_threshold_multiplier), 2)},
        )
