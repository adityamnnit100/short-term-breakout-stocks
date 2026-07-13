"""Base-quality setup gate."""

from __future__ import annotations

from typing import List

import pandas as pd

from quality_filter.models import QualityContext
from .models import SetupGate, SetupGateResult


class BaseQualityGate(SetupGate):
    name = "base_quality"

    def evaluate(self, context: QualityContext) -> SetupGateResult:
        cfg = context.config
        close = context.close.tail(max(cfg.setup_volume_long_window, 40)).dropna()
        if close.empty:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Missing close history"], metrics={"reason": "missing_close"})

        recent = close.tail(min(len(close), cfg.setup_volume_long_window)).copy()
        high = context.high.tail(len(recent)).dropna()
        low = context.low.tail(len(recent)).dropna()
        if high.empty or low.empty:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Missing OHLC history"], metrics={"reason": "missing_ohlc"})

        base_high = float(recent.max())
        base_low = float(recent.min())
        depth_pct = ((base_high - base_low) / base_high * 100.0) if base_high > 0 else 0.0
        duration_weeks = len(recent) / 5.0
        midpoint = max(len(recent) // 2, 1)
        first_range = float(recent.iloc[:midpoint].max() - recent.iloc[:midpoint].min())
        second_range = float(recent.iloc[midpoint:].max() - recent.iloc[midpoint:].min()) if len(recent.iloc[midpoint:]) else first_range
        symmetry_delta = abs(first_range - second_range) / max(first_range, second_range, 1e-9)
        pullbacks = int((recent.diff().dropna() < 0).sum())
        higher_lows = bool(context.higher_lows)
        tight_closes = float(recent.tail(10).std() / max(float(recent.tail(10).mean()), 1e-9))
        stability = 1.0 - min(tight_closes * 10.0, 1.0)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if depth_pct <= cfg.setup_max_base_depth_pct:
            score += 30.0
            reasons.append(f"{round(depth_pct, 1)}% base depth")
        elif depth_pct <= cfg.setup_max_base_depth_pct * 1.5:
            score += 15.0
            weaknesses.append("Base slightly deep")
        else:
            weaknesses.append("Base too deep")

        if duration_weeks >= cfg.setup_min_base_weeks:
            score += 20.0
            reasons.append(f"{round(duration_weeks, 1)} weeks flat base")
        elif duration_weeks >= max(cfg.setup_min_base_weeks * 0.5, 1):
            score += 10.0
            weaknesses.append("Base too short")
        else:
            weaknesses.append("Base duration weak")

        if symmetry_delta <= 0.35:
            score += 15.0
            reasons.append("Base symmetry constructive")
        elif symmetry_delta <= 0.55:
            score += 8.0
            weaknesses.append("Base slightly asymmetric")
        else:
            weaknesses.append("Base symmetry poor")

        if pullbacks <= 4:
            score += 10.0
            reasons.append("Controlled pullbacks")
        else:
            weaknesses.append("Too many pullbacks")

        if higher_lows:
            score += 10.0
            reasons.append("Higher lows intact")
        else:
            weaknesses.append("Higher lows not confirmed")

        if tight_closes <= 0.03:
            score += 10.0
            reasons.append("Tight closes")
        else:
            weaknesses.append("Closes too loose")

        if stability >= 0.7:
            score += 5.0
            reasons.append("Price stability constructive")
        else:
            weaknesses.append("Price stability weak")

        metrics = {
            "base_depth_pct": round(depth_pct, 2),
            "base_duration_weeks": round(duration_weeks, 2),
            "base_symmetry_delta": round(symmetry_delta, 2),
            "pullbacks": pullbacks,
            "higher_lows": higher_lows,
            "tight_closes": round(tight_closes, 4),
            "price_stability": round(stability, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return SetupGateResult(self.name, final_score, final_score >= 60.0, reasons=reasons, weaknesses=weaknesses, metrics=metrics)
