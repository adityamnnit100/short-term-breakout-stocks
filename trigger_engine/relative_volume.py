"""Relative volume trigger module."""

from __future__ import annotations

from typing import List

from .models import TriggerContext, TriggerModule, TriggerModuleResult


class RelativeVolumeModule(TriggerModule):
    name = "relative_volume"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        cfg = context.config
        volume = context.frame["Volume"].astype(float).tail(max(cfg.volume_sma_window, 20)).dropna()
        if volume.empty:
            return TriggerModuleResult(self.name, False, weaknesses=["Missing volume history"], metrics={"reason": "missing_history"})

        current = float(volume.iloc[-1])
        avg_5 = float(volume.tail(min(len(volume), 5)).mean())
        avg_10 = float(volume.tail(min(len(volume), 10)).mean())
        avg_20 = float(volume.tail(min(len(volume), 20)).mean())
        rvol_5 = current / max(avg_5, 1e-9)
        rvol_10 = current / max(avg_10, 1e-9)
        rvol_20 = current / max(avg_20, 1e-9)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []
        if rvol_5 >= cfg.trigger_relative_volume_5d_min:
            score += 35.0
            reasons.append("5-day relative volume strong")
        else:
            weaknesses.append("5-day RVOL weak")
        if rvol_10 >= cfg.trigger_relative_volume_10d_min:
            score += 35.0
            reasons.append("10-day relative volume strong")
        else:
            weaknesses.append("10-day RVOL weak")
        if rvol_20 >= cfg.trigger_relative_volume_20d_min:
            score += 30.0
            reasons.append("20-day relative volume constructive")
        else:
            weaknesses.append("20-day RVOL weak")

        metrics = {
            "current_volume": round(current, 2),
            "rvol_5d": round(rvol_5, 2),
            "rvol_10d": round(rvol_10, 2),
            "rvol_20d": round(rvol_20, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return TriggerModuleResult(
            self.name,
            passed=rvol_5 >= cfg.trigger_relative_volume_5d_min and rvol_10 >= cfg.trigger_relative_volume_10d_min and rvol_20 >= cfg.trigger_relative_volume_20d_min,
            score=final_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
