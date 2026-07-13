"""Price-structure setup gate."""

from __future__ import annotations

from typing import List

import pandas as pd

from quality_filter.models import QualityContext
from .models import SetupGate, SetupGateResult


class StructureGate(SetupGate):
    name = "structure"

    def evaluate(self, context: QualityContext) -> SetupGateResult:
        cfg = context.config
        close = context.close.tail(120).dropna()
        if close.empty:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Missing close history"], metrics={"reason": "missing_close"})

        weekly = close.resample("W").last() if isinstance(close.index, pd.DatetimeIndex) else close
        daily_std = float(close.tail(10).std() or 0.0)
        weekly_std = float(weekly.tail(8).std() or 0.0) if len(weekly) >= 4 else daily_std
        higher_lows = bool(context.higher_lows)
        flat_base = float(close.tail(20).max() - close.tail(20).min()) / max(float(close.iloc[-1]), 1e-9) <= 0.08
        triangle = bool(higher_lows and float(context.high.tail(20).max() - context.high.tail(20).min()) / max(float(context.high.tail(20).max()), 1e-9) <= 0.06)
        cup_like = bool(float(close.tail(30).min()) < float(close.tail(10).mean()) * 0.95 and float(close.tail(10).mean()) >= float(close.tail(30).mean()))
        recent_std = float(close.tail(10).std() or 0.0)
        prior_std = float(close.tail(30).std() or 0.0)
        vcp_like = bool(prior_std > 0 and recent_std <= prior_std * 0.8)
        tight_daily_closes = daily_std / max(float(close.tail(10).mean()), 1e-9) <= 0.02
        tight_weekly_closes = weekly_std / max(float(weekly.tail(min(len(weekly), 8)).mean()), 1e-9) <= 0.03 if len(weekly) else False
        compression_triangle = bool(flat_base or triangle or vcp_like)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if tight_daily_closes:
            score += 20.0
            reasons.append("Tight daily closes")
        else:
            weaknesses.append("Daily closes loose")

        if tight_weekly_closes:
            score += 20.0
            reasons.append("Tight weekly closes")

        if higher_lows:
            score += 15.0
            reasons.append("Higher lows")
        else:
            weaknesses.append("Higher lows not confirmed")

        if compression_triangle:
            score += 20.0
            reasons.append("Compression triangle")
        else:
            weaknesses.append("No compression triangle")

        if flat_base:
            score += 15.0
            reasons.append("Flat base")
        if cup_like:
            score += 10.0
            reasons.append("Cup-like structure")
        if vcp_like:
            score += 10.0
            reasons.append("VCP structure")

        metrics = {
            "daily_std": round(daily_std, 4),
            "weekly_std": round(weekly_std, 4),
            "higher_lows": higher_lows,
            "flat_base": flat_base,
            "triangle": triangle,
            "cup_like": cup_like,
            "vcp_like": vcp_like,
            "tight_daily_closes": tight_daily_closes,
            "tight_weekly_closes": tight_weekly_closes,
        }
        final_score = round(min(score, 100.0), 2)
        return SetupGateResult(self.name, final_score, final_score >= cfg.setup_min_structure_score, reasons=reasons, weaknesses=weaknesses, metrics=metrics)
