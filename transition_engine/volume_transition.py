"""Volume transition gate."""

from __future__ import annotations

from typing import List

import numpy as np

from .models import TransitionContext, TransitionGate, TransitionGateResult


class VolumeTransitionGate(TransitionGate):
    name = "volume_transition"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        volume = context.quality.volume.tail(max(context.config.transition_history_window + 10, 20)).dropna()
        close = context.quality.close.tail(len(volume)).dropna()
        if volume.empty or close.empty:
            return TransitionGateResult(self.name, 0.0, False, weaknesses=["Missing volume history"], metrics={"reason": "missing_volume"})

        vol_3 = float(volume.tail(min(len(volume), 3)).mean())
        vol_5 = float(volume.tail(min(len(volume), 5)).mean())
        vol_10 = float(volume.tail(min(len(volume), 10)).mean())
        vol_20 = float(volume.tail(min(len(volume), 20)).mean())
        current = float(volume.iloc[-1])

        up_mask = close.diff().fillna(0) > 0
        down_mask = close.diff().fillna(0) < 0
        up_volume_5 = float(volume.tail(5)[up_mask.tail(5)].mean()) if up_mask.tail(5).any() else 0.0
        down_volume_5 = float(volume.tail(5)[down_mask.tail(5)].mean()) if down_mask.tail(5).any() else 0.0
        up_volume_10 = float(volume.tail(10)[up_mask.tail(10)].mean()) if up_mask.tail(10).any() else 0.0
        down_volume_10 = float(volume.tail(10)[down_mask.tail(10)].mean()) if down_mask.tail(10).any() else 0.0

        expansion_ratio = current / max(vol_10, 1e-9)
        transition_ratio = vol_3 / max(vol_10, 1e-9)
        contraction_ratio = vol_5 / max(vol_20, 1e-9)
        volume_slope = float(np.polyfit(np.arange(min(len(volume), 10), dtype=float), volume.tail(min(len(volume), 10)).astype(float), 1)[0]) if len(volume) >= 2 else 0.0
        dry_up_to_expansion = vol_3 >= vol_5 and vol_5 >= vol_10 and current >= vol_10
        supply_absorption = down_volume_5 > 0 and up_volume_5 >= down_volume_5 * 0.9
        participation_rising = up_volume_10 >= up_volume_5 and down_volume_10 <= max(down_volume_5, 1e-9)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if expansion_ratio >= 1.2:
            score += 20.0
            reasons.append("Relative volume expanding")
        elif expansion_ratio >= 1.0:
            score += 12.0
        else:
            weaknesses.append("Relative volume not expanding")

        if transition_ratio >= 1.1:
            score += 15.0
            reasons.append("Short-term volume trend rising")
        elif transition_ratio >= 0.95:
            score += 8.0
        else:
            weaknesses.append("Short-term volume trend weak")

        if contraction_ratio >= 1.0:
            score += 10.0
        else:
            weaknesses.append("Volume contraction not stabilizing")

        if dry_up_to_expansion:
            score += 20.0
            reasons.append("Dry-up transitioning into expansion")
        else:
            weaknesses.append("Dry-up to expansion not confirmed")

        if supply_absorption:
            score += 15.0
            reasons.append("Up-volume absorbing down-volume")
        elif down_volume_5 == 0 and up_volume_5 > 0:
            score += 10.0
        else:
            weaknesses.append("Down-volume absorption weak")

        if participation_rising:
            score += 10.0
            reasons.append("Institutional participation improving")
        else:
            weaknesses.append("Participation not clearly improving")

        if volume_slope > 0:
            score += 10.0
        else:
            weaknesses.append("Volume slope negative")

        metrics = {
            "volume_3d_avg": round(vol_3, 2),
            "volume_5d_avg": round(vol_5, 2),
            "volume_10d_avg": round(vol_10, 2),
            "volume_20d_avg": round(vol_20, 2),
            "current_volume": round(current, 2),
            "expansion_ratio": round(expansion_ratio, 2),
            "transition_ratio": round(transition_ratio, 2),
            "contraction_ratio": round(contraction_ratio, 2),
            "up_volume_5d": round(up_volume_5, 2),
            "down_volume_5d": round(down_volume_5, 2),
            "up_volume_10d": round(up_volume_10, 2),
            "down_volume_10d": round(down_volume_10, 2),
            "volume_slope": round(volume_slope, 4),
            "dry_up_to_expansion": dry_up_to_expansion,
        }
        final_score = round(min(score, 100.0), 2)
        return TransitionGateResult(
            self.name,
            final_score,
            final_score >= context.config.transition_min_volume_transition_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
