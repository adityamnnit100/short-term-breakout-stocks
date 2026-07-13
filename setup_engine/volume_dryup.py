"""Volume dry-up setup gate."""

from __future__ import annotations

from typing import List

import pandas as pd

from quality_filter.models import QualityContext
from .models import SetupGate, SetupGateResult


class VolumeDryupGate(SetupGate):
    name = "volume_dryup"

    def evaluate(self, context: QualityContext) -> SetupGateResult:
        cfg = context.config
        volume = context.volume.tail(max(cfg.setup_volume_long_window, 20)).dropna()
        close = context.close.tail(len(volume)).dropna()
        if volume.empty or close.empty:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Missing volume history"], metrics={"reason": "missing_volume"})

        long_avg = float(volume.tail(cfg.setup_volume_long_window).mean()) if len(volume) >= cfg.setup_volume_long_window else float(volume.mean())
        short_avg = float(volume.tail(cfg.setup_volume_short_window).mean()) if len(volume) >= cfg.setup_volume_short_window else float(volume.tail(max(len(volume) // 2, 1)).mean())
        current = float(volume.iloc[-1])
        volume_trend = float(volume.tail(10).diff().mean())
        down_days = int((close.diff().dropna() < 0).tail(20).sum())
        up_days = int((close.diff().dropna() > 0).tail(20).sum())
        up_slice = volume.tail(20)[close.diff().tail(20).fillna(0) > 0]
        down_slice = volume.tail(20)[close.diff().tail(20).fillna(0) < 0]
        up_volume = float(up_slice.mean()) if not up_slice.empty and pd.notna(up_slice.mean()) else 0.0
        down_volume = float(down_slice.mean()) if not down_slice.empty and pd.notna(down_slice.mean()) else 0.0
        quiet_consolidation = current <= min(volume.tail(10).mean(), long_avg) * 0.9
        supply_exhaustion = current <= float(volume.tail(20).min())
        ratio = current / long_avg if long_avg > 0 else 0.0
        trend_ratio = short_avg / long_avg if long_avg > 0 else 0.0
        up_down_ratio = up_volume / max(down_volume, 1e-9) if down_volume > 0 else (2.0 if up_volume > 0 else 0.0)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if ratio <= 0.7:
            score += 25.0
            reasons.append("Low relative volume")
        elif ratio <= 0.85:
            score += 15.0
        else:
            weaknesses.append("Volume not yet dry")

        if trend_ratio <= 0.9:
            score += 20.0
            reasons.append("Volume trend fading")
        elif trend_ratio <= 0.97:
            score += 10.0

        if up_down_ratio <= 0.8:
            score += 15.0
            reasons.append("Down-volume absorption")
        elif up_down_ratio <= 1.0:
            score += 8.0

        if quiet_consolidation:
            score += 20.0
            reasons.append("Quiet consolidation")
        else:
            weaknesses.append("Not quiet enough")

        if supply_exhaustion:
            score += 15.0
            reasons.append("Supply exhaustion")

        if down_days > up_days:
            score += 5.0
            reasons.append("Controlled down days")

        metrics = {
            "volume_long_avg": round(long_avg, 2),
            "volume_short_avg": round(short_avg, 2),
            "volume_current": round(current, 2),
            "volume_trend": round(volume_trend, 2),
            "up_volume": round(up_volume, 2),
            "down_volume": round(down_volume, 2),
            "up_down_ratio": round(up_down_ratio, 2),
            "quiet_consolidation": quiet_consolidation,
            "supply_exhaustion": supply_exhaustion,
        }
        final_score = round(min(score, 100.0), 2)
        return SetupGateResult(self.name, final_score, final_score >= cfg.setup_min_volume_score, reasons=reasons, weaknesses=weaknesses, metrics=metrics)
