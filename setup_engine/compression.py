"""Volatility-contraction setup gate."""

from __future__ import annotations

from typing import List

import pandas as pd

from quality_filter.models import QualityContext
from .models import SetupGate, SetupGateResult


class CompressionGate(SetupGate):
    name = "compression"

    def evaluate(self, context: QualityContext) -> SetupGateResult:
        cfg = context.config
        close = context.close.tail(60).dropna()
        if close.empty:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Missing close history"], metrics={"reason": "missing_close"})

        atr_series = context.atr.tail(60).dropna()
        high = context.high.tail(60).dropna()
        low = context.low.tail(60).dropna()
        if atr_series.empty or high.empty or low.empty:
            return SetupGateResult(self.name, 0.0, False, weaknesses=["Missing volatility history"], metrics={"reason": "missing_volatility"})

        atr_recent = float(atr_series.tail(5).mean())
        atr_prior = float(atr_series.head(max(len(atr_series) - 5, 1)).tail(10).mean()) if len(atr_series) > 10 else float(atr_series.mean())
        std_recent = float(close.tail(10).std() or 0.0)
        std_prior = float(close.tail(30).std() or 0.0)
        range_recent = float((high.tail(5).max() - low.tail(5).min()) if len(high) >= 5 and len(low) >= 5 else high.max() - low.min())
        range_prior = float((high.tail(20).max() - low.tail(20).min()) if len(high) >= 20 and len(low) >= 20 else high.max() - low.min())
        bb_mean = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bbw = ((bb_std * 4.0) / bb_mean.replace(0, pd.NA)) * 100.0
        bbw_recent = float(bbw.tail(5).mean()) if not bbw.empty else 0.0
        bbw_prior = float(bbw.head(max(len(bbw) - 5, 1)).tail(10).mean()) if len(bbw) > 10 else float(bbw.mean()) if not bbw.empty else 0.0
        latest_atr = float(atr_series.iloc[-1])
        keltner_ratio = (latest_atr / max(float(close.iloc[-1]), 1e-9)) * 100.0

        def _pct_change(current: float, reference: float) -> float:
            if reference is None or reference <= 0:
                return 0.0
            return ((current / reference) - 1.0) * 100.0

        atr_contraction_pct = _pct_change(atr_recent, atr_prior)
        std_contraction_pct = _pct_change(std_recent, std_prior)
        range_contraction_pct = _pct_change(range_recent, range_prior)
        bbw_contraction_pct = _pct_change(bbw_recent, bbw_prior)
        contraction_waves = int((atr_series.diff().dropna() < 0).tail(10).sum())
        nr7 = bool((high.tail(7).max() - low.tail(7).min()) <= (high.tail(20).max() - low.tail(20).min()) * 0.6)
        nr4 = bool((high.tail(4).max() - low.tail(4).min()) <= (high.tail(20).max() - low.tail(20).min()) * 0.4)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if atr_contraction_pct <= -10:
            score += 20.0
            reasons.append(f"{round(abs(atr_contraction_pct), 1)}% ATR contraction")
        elif atr_contraction_pct <= -5:
            score += 12.0
            weaknesses.append("ATR contraction moderate")
        else:
            weaknesses.append("ATR not contracting enough")

        if std_contraction_pct <= -10:
            score += 15.0
            reasons.append("Standard deviation contraction")
        elif std_contraction_pct <= -5:
            score += 8.0
        else:
            weaknesses.append("Std dev not contracting")

        if range_contraction_pct <= -10:
            score += 15.0
            reasons.append("Range contraction")
        elif range_contraction_pct <= -5:
            score += 8.0
        else:
            weaknesses.append("Range not contracting")

        if bbw_contraction_pct <= -10:
            score += 15.0
            reasons.append("Bollinger Band Width contracting")
        elif bbw_contraction_pct <= -5:
            score += 8.0
        else:
            weaknesses.append("BBW not tight")

        if contraction_waves >= 4:
            score += 10.0
            reasons.append("Multiple contraction waves")
        else:
            weaknesses.append("Contraction waves limited")

        if nr7:
            score += 10.0
            reasons.append("NR7")
        if nr4:
            score += 5.0
            reasons.append("NR4")

        if keltner_ratio <= cfg.setup_max_distance_to_high_pct:
            score += 10.0
            reasons.append("Keltner compression")
        else:
            weaknesses.append("Keltner compression weak")

        metrics = {
            "atr_contraction_pct": round(atr_contraction_pct, 2),
            "std_contraction_pct": round(std_contraction_pct, 2),
            "range_contraction_pct": round(range_contraction_pct, 2),
            "bbw_contraction_pct": round(bbw_contraction_pct, 2),
            "contraction_waves": contraction_waves,
            "nr7": nr7,
            "nr4": nr4,
            "keltner_ratio_pct": round(keltner_ratio, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return SetupGateResult(self.name, final_score, final_score >= cfg.setup_min_compression_score, reasons=reasons, weaknesses=weaknesses, metrics=metrics)
