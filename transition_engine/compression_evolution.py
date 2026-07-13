"""Compression evolution gate."""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from .models import TransitionContext, TransitionGate, TransitionGateResult


def _pct_change(current: float, reference: float) -> float:
    if reference is None or reference <= 0:
        return 0.0
    return ((current / reference) - 1.0) * 100.0


def _trend_slope(values: pd.Series) -> float:
    clean = values.dropna().astype(float)
    if len(clean) < 2:
        return 0.0
    x = np.arange(len(clean), dtype=float)
    try:
        return float(np.polyfit(x, clean.to_numpy(), 1)[0])
    except Exception:
        return 0.0


class CompressionEvolutionGate(TransitionGate):
    name = "compression_evolution"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        close = context.quality.close.tail(max(context.config.transition_history_window + 20, 40)).dropna()
        atr_series = context.quality.atr.tail(len(close)).dropna()
        high = context.quality.high.tail(len(close)).dropna()
        low = context.quality.low.tail(len(close)).dropna()
        if close.empty or atr_series.empty or high.empty or low.empty:
            return TransitionGateResult(self.name, 0.0, False, weaknesses=["Missing compression history"], metrics={"reason": "missing_history"})

        close = close.tail(min(len(close), len(atr_series), len(high), len(low)))
        atr_series = atr_series.tail(len(close))
        high = high.tail(len(close))
        low = low.tail(len(close))

        atr_3 = float(atr_series.tail(min(len(atr_series), 3)).mean())
        atr_5 = float(atr_series.tail(min(len(atr_series), 5)).mean())
        atr_10 = float(atr_series.tail(min(len(atr_series), 10)).mean())
        atr_20 = float(atr_series.tail(min(len(atr_series), 20)).mean())

        std_3 = float(close.tail(min(len(close), 3)).std() or 0.0)
        std_5 = float(close.tail(min(len(close), 5)).std() or 0.0)
        std_10 = float(close.tail(min(len(close), 10)).std() or 0.0)
        std_20 = float(close.tail(min(len(close), 20)).std() or 0.0)

        range_3 = float(high.tail(min(len(high), 3)).max() - low.tail(min(len(low), 3)).min())
        range_5 = float(high.tail(min(len(high), 5)).max() - low.tail(min(len(low), 5)).min())
        range_10 = float(high.tail(min(len(high), 10)).max() - low.tail(min(len(low), 10)).min())
        range_20 = float(high.tail(min(len(high), 20)).max() - low.tail(min(len(low), 20)).min())

        bbw = ((close.rolling(20).std() * 4.0) / close.rolling(20).mean().replace(0, pd.NA)) * 100.0
        bbw_3 = float(bbw.tail(min(len(bbw.dropna()), 3)).mean()) if not bbw.dropna().empty else 0.0
        bbw_5 = float(bbw.tail(min(len(bbw.dropna()), 5)).mean()) if not bbw.dropna().empty else 0.0
        bbw_10 = float(bbw.tail(min(len(bbw.dropna()), 10)).mean()) if not bbw.dropna().empty else 0.0
        bbw_20 = float(bbw.tail(min(len(bbw.dropna()), 20)).mean()) if not bbw.dropna().empty else 0.0

        nr7_frequency = int(sum((high.shift(i).tail(7).max() - low.shift(i).tail(7).min()) <= (high.tail(20).max() - low.tail(20).min()) * 0.7 for i in range(1, 8)))
        nr4_frequency = int(sum((high.shift(i).tail(4).max() - low.shift(i).tail(4).min()) <= (high.tail(20).max() - low.tail(20).min()) * 0.5 for i in range(1, 5)))

        atr_trend = _pct_change(atr_3, atr_10)
        std_trend = _pct_change(std_3, std_10)
        range_trend = _pct_change(range_3, range_10)
        bbw_trend = _pct_change(bbw_3, bbw_10)
        contraction_improving = atr_3 < atr_10 and std_3 < std_10 and range_3 < range_10 and bbw_3 < bbw_10
        tightening_rate = _trend_slope(atr_series.tail(min(len(atr_series), 10)))

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if atr_trend <= -10:
            score += 20.0
            reasons.append("ATR tightening")
        elif atr_trend <= -5:
            score += 12.0
        else:
            weaknesses.append("ATR trend not tightening")

        if std_trend <= -10:
            score += 15.0
            reasons.append("Standard deviation tightening")
        elif std_trend <= -5:
            score += 8.0
        else:
            weaknesses.append("Std dev trend weak")

        if range_trend <= -10:
            score += 15.0
            reasons.append("Range tightening")
        elif range_trend <= -5:
            score += 8.0
        else:
            weaknesses.append("Range trend weak")

        if bbw_trend <= -10:
            score += 15.0
            reasons.append("Bollinger width tightening")
        elif bbw_trend <= -5:
            score += 8.0
        else:
            weaknesses.append("BBW trend weak")

        if contraction_improving:
            score += 20.0
            reasons.append("Compression getting tighter")
        else:
            weaknesses.append("Compression not clearly improving")

        if nr7_frequency >= 3:
            score += 10.0
            reasons.append("NR7 frequency supportive")
        elif nr7_frequency >= 1:
            score += 5.0

        if nr4_frequency >= 2:
            score += 5.0
            reasons.append("NR4 frequency supportive")

        if tightening_rate < 0:
            score += 10.0
        else:
            weaknesses.append("Compression trend flattening")

        metrics = {
            "atr_3d": round(atr_3, 4),
            "atr_5d": round(atr_5, 4),
            "atr_10d": round(atr_10, 4),
            "atr_20d": round(atr_20, 4),
            "std_3d": round(std_3, 4),
            "std_5d": round(std_5, 4),
            "std_10d": round(std_10, 4),
            "std_20d": round(std_20, 4),
            "range_3d": round(range_3, 4),
            "range_5d": round(range_5, 4),
            "range_10d": round(range_10, 4),
            "range_20d": round(range_20, 4),
            "bbw_3d": round(bbw_3, 4),
            "bbw_5d": round(bbw_5, 4),
            "bbw_10d": round(bbw_10, 4),
            "bbw_20d": round(bbw_20, 4),
            "nr7_frequency": nr7_frequency,
            "nr4_frequency": nr4_frequency,
            "contraction_improving": contraction_improving,
            "tightening_rate": round(tightening_rate, 4),
        }
        final_score = round(min(score, 100.0), 2)
        return TransitionGateResult(
            self.name,
            final_score,
            final_score >= context.config.transition_min_compression_evolution_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
