"""Risk structure setup gate."""

from __future__ import annotations

from typing import List

from quality_filter.models import QualityContext
from .models import SetupGate, SetupGateResult


class RiskGate(SetupGate):
    name = "risk"

    def evaluate(self, context: QualityContext) -> SetupGateResult:
        cfg = context.config
        close = context.latest_close
        atr_value = context.latest_atr
        if close <= 0 or atr_value <= 0:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Invalid ATR/close"], metrics={"reason": "invalid_price_or_atr"})

        base_floor = float(context.low.tail(20).dropna().min()) if not context.low.tail(20).dropna().empty else 0.0
        stop_loss = close - atr_value * 1.5
        risk_pct = (atr_value / close) * 100.0
        distance_to_stop_pct = ((close - stop_loss) / close) * 100.0
        base_failure_risk = ((close - base_floor) / close) * 100.0 if base_floor > 0 else 0.0
        reward = (context.recent_high_40d - close) if context.recent_high_40d > close else atr_value * 2.0
        risk_reward = reward / max((close - stop_loss), 1e-9)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if distance_to_stop_pct <= 4.0:
            score += 25.0
            reasons.append("Tight stop distance")
        elif distance_to_stop_pct <= 6.0:
            score += 15.0
        else:
            weaknesses.append("Stop too wide")

        if risk_pct <= 4.0:
            score += 20.0
            reasons.append("ATR risk contained")
        elif risk_pct <= 6.0:
            score += 10.0
        else:
            weaknesses.append("ATR risk elevated")

        if base_failure_risk <= 8.0:
            score += 20.0
            reasons.append("Base failure risk acceptable")
        elif base_failure_risk <= 12.0:
            score += 10.0
        else:
            weaknesses.append("Base failure risk high")

        if risk_reward >= 2.0:
            score += 25.0
            reasons.append("Positive risk/reward")
        elif risk_reward >= 1.5:
            score += 12.0
        else:
            weaknesses.append("Risk/reward weak")

        metrics = {
            "stop_loss": round(stop_loss, 2),
            "risk_pct": round(risk_pct, 2),
            "distance_to_stop_pct": round(distance_to_stop_pct, 2),
            "base_failure_risk_pct": round(base_failure_risk, 2),
            "risk_reward": round(risk_reward, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return SetupGateResult(self.name, final_score, final_score >= cfg.setup_min_risk_score, reasons=reasons, weaknesses=weaknesses, metrics=metrics)
