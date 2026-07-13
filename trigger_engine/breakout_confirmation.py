"""Breakout confirmation trigger module."""

from __future__ import annotations

from typing import List

from .models import TriggerContext, TriggerModule, TriggerModuleResult


class BreakoutConfirmationModule(TriggerModule):
    name = "breakout_confirmation"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        cfg = context.config
        close = context.frame["Close"].astype(float).tail(20).dropna()
        high = context.frame["High"].astype(float).tail(20).dropna()
        volume = context.frame["Volume"].astype(float).tail(20).dropna()
        if close.empty or high.empty or volume.empty:
            return TriggerModuleResult(self.name, False, weaknesses=["Missing breakout history"], metrics={"reason": "missing_history"})

        resistance = float(context.transition.metrics.get("resistance_pressure", {}).get("resistance_level", context.quality.recent_high_40d))
        current_close = float(close.iloc[-1])
        current_volume = float(volume.iloc[-1])
        avg_volume = float(volume.tail(min(len(volume), 10)).mean())
        volume_ratio = current_volume / max(avg_volume, 1e-9)
        breakout_buffer = resistance * (cfg.trigger_breakout_buffer_pct / 100.0)
        close_above_breakout = current_close >= resistance + breakout_buffer
        close_above_prior = current_close >= float(close.iloc[-2]) if len(close) > 1 else True
        false_breakout_risk = current_close < resistance and float(close.iloc[-1]) <= float(high.iloc[-1]) * 0.98
        breakout_quality = current_close >= float(high.tail(5).max()) * 0.995

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []
        if close_above_breakout:
            score += 40.0
            reasons.append("Resistance broken")
        else:
            weaknesses.append("Resistance not yet broken")
        if close_above_prior:
            score += 20.0
            reasons.append("Close above prior session")
        else:
            weaknesses.append("Close failed to improve")
        if volume_ratio >= cfg.trigger_breakout_volume_ratio_min:
            score += 25.0
            reasons.append("Breakout volume confirmed")
        else:
            weaknesses.append("Breakout volume weak")
        if breakout_quality:
            score += 15.0
            reasons.append("Breakout quality constructive")
        else:
            weaknesses.append("Breakout quality weak")
        if false_breakout_risk:
            weaknesses.append("False breakout risk elevated")

        metrics = {
            "resistance": round(resistance, 2),
            "current_close": round(current_close, 2),
            "volume_ratio": round(volume_ratio, 2),
            "close_above_breakout": close_above_breakout,
            "breakout_quality": breakout_quality,
            "false_breakout_risk": false_breakout_risk,
        }
        final_score = round(min(score, 100.0), 2)
        return TriggerModuleResult(
            self.name,
            passed=close_above_breakout and volume_ratio >= cfg.trigger_breakout_volume_ratio_min and breakout_quality and not false_breakout_risk,
            score=final_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
