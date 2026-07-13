"""Trend qualification gate."""

from __future__ import annotations

from .models import GateResult, QualityContext, QualityGate


class TrendGate(QualityGate):
    name = "trend"

    def evaluate(self, context: QualityContext) -> GateResult:
        cfg = context.config
        reasons = []

        if cfg.quality_require_price_above_ema200 and not (context.latest_close > context.latest_ema200):
            return GateResult(name=self.name, passed=False, reason="Trend Template Failed", detail={"price_above_ema200": False})

        if cfg.quality_require_ema_alignment and not (context.latest_ema20 > context.latest_ema50 > context.latest_ema200):
            return GateResult(name=self.name, passed=False, reason="EMA Alignment Failed", detail={"ema_alignment": False})

        if cfg.quality_require_trend_template and not context.trend_template_pass:
            return GateResult(name=self.name, passed=False, reason="Trend Template Failed", detail={"trend_template_pass": False})

        if cfg.quality_require_higher_highs and not context.higher_highs:
            return GateResult(name=self.name, passed=False, reason="Higher Highs Failed", detail={"higher_highs": False})

        if cfg.quality_require_higher_lows and not context.higher_lows:
            return GateResult(name=self.name, passed=False, reason="Higher Lows Failed", detail={"higher_lows": False})

        reasons.extend(["Trend template qualified" if context.trend_template_pass else "Trend template not required"])
        return GateResult(name=self.name, passed=True, detail={"trend_template_pass": context.trend_template_pass, "reasons": reasons})
