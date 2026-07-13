"""Pocket pivot trigger module."""

from __future__ import annotations

from typing import List

from .models import TriggerContext, TriggerModule, TriggerModuleResult


class PocketPivotModule(TriggerModule):
    name = "pocket_pivot"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        cfg = context.config
        frame = context.frame.tail(max(cfg.contraction_window, 10)).copy()
        if frame.empty:
            return TriggerModuleResult(self.name, False, weaknesses=["Missing daily history"], metrics={"reason": "missing_history"})

        close = frame["Close"].astype(float)
        high = frame["High"].astype(float)
        low = frame["Low"].astype(float)
        volume = frame["Volume"].astype(float)

        current_close = float(close.iloc[-1])
        current_volume = float(volume.iloc[-1])
        current_high = float(high.iloc[-1])
        current_low = float(low.iloc[-1])
        day_range = max(current_high - current_low, 1e-9)
        close_location = (current_close - current_low) / day_range

        prior_volume = volume.iloc[:-1]
        down_mask = close.diff().fillna(0).iloc[:-1] < 0
        down_volumes = prior_volume[down_mask]
        pivot_volume = float(down_volumes.max()) if not down_volumes.empty else float(prior_volume.tail(10).max())
        volume_ratio = current_volume / max(pivot_volume, 1e-9)
        prior_high = float(high.iloc[:-1].tail(10).max()) if len(high) > 1 else current_high
        strong_close = close_location >= cfg.trigger_pocket_pivot_close_location_min
        pivot_quality = current_close >= prior_high * (1 - cfg.trigger_breakout_buffer_pct / 100.0)
        volume_expansion = volume_ratio >= cfg.trigger_pocket_pivot_volume_ratio
        higher_close = current_close > float(close.iloc[-2]) if len(close) > 1 else True

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []
        if volume_expansion:
            score += 40.0
            reasons.append("Volume expansion pocket pivot")
        else:
            weaknesses.append("Pocket pivot volume expansion absent")
        if strong_close:
            score += 25.0
            reasons.append("Strong close")
        else:
            weaknesses.append("Close not strong enough")
        if pivot_quality:
            score += 20.0
            reasons.append("Pivot quality constructive")
        else:
            weaknesses.append("Pivot quality weak")
        if higher_close:
            score += 15.0
            reasons.append("Higher close")
        else:
            weaknesses.append("Close failed to improve")

        metrics = {
            "current_close": round(current_close, 2),
            "current_volume": round(current_volume, 2),
            "volume_ratio": round(volume_ratio, 2),
            "close_location": round(close_location, 2),
            "pivot_quality": pivot_quality,
            "strong_close": strong_close,
        }
        final_score = round(min(score, 100.0), 2)
        return TriggerModuleResult(
            self.name,
            passed=volume_expansion and strong_close and pivot_quality,
            score=final_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
