"""Relative-strength acceleration gate."""

from __future__ import annotations

from typing import List

import numpy as np

from scanner.indicators import safe_pct_change

from .models import TransitionContext, TransitionGate, TransitionGateResult


def _slope(values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    x = np.arange(values.size, dtype=float)
    try:
        return float(np.polyfit(x, values.astype(float), 1)[0])
    except Exception:
        return 0.0


class RSAccelerationGate(TransitionGate):
    name = "rs_acceleration"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        close = context.quality.close.tail(max(context.config.transition_history_window + 10, 20)).dropna()
        if close.empty:
            return TransitionGateResult(self.name, 0.0, False, weaknesses=["Missing price history"], metrics={"reason": "missing_close"})

        rolling_mean = close.rolling(20).mean().replace(0, np.nan)
        rs_proxy = (close / rolling_mean * 100.0).dropna()
        if rs_proxy.empty:
            return TransitionGateResult(self.name, 0.0, False, weaknesses=["Missing RS proxy history"], metrics={"reason": "missing_rs_proxy"})

        current = float(rs_proxy.iloc[-1])
        last_1 = float(rs_proxy.iloc[-1])
        last_3 = float(rs_proxy.tail(min(len(rs_proxy), 3)).mean())
        last_5 = float(rs_proxy.tail(min(len(rs_proxy), 5)).mean())
        last_10 = float(rs_proxy.tail(min(len(rs_proxy), 10)).mean())

        slope_3d = current - last_3
        slope_5d = current - last_5
        slope_10d = current - last_10
        accel = (current - last_3) - (last_3 - last_5)
        trend_slope = _slope(rs_proxy.tail(min(len(rs_proxy), 10)).to_numpy())
        momentum = safe_pct_change(current, last_10)
        new_high = bool(current >= float(rs_proxy.tail(min(len(rs_proxy), 10)).max()) * 0.995)
        leadership = bool(context.quality.latest_close >= context.quality.recent_high_20d * 0.97 and context.quality.relative_strength >= 50.0)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if slope_3d > 2:
            score += 20.0
            reasons.append("RS slope improving over 3 sessions")
        elif slope_3d > 0.5:
            score += 12.0
        else:
            weaknesses.append("3-day RS slope weak")

        if slope_5d > 2:
            score += 20.0
            reasons.append("RS slope improving over 5 sessions")
        elif slope_5d > 0.5:
            score += 12.0
        else:
            weaknesses.append("5-day RS slope weak")

        if accel > 0.5:
            score += 20.0
            reasons.append("RS acceleration positive")
        elif accel > 0:
            score += 10.0
        else:
            weaknesses.append("RS acceleration stalled")

        if momentum > 2:
            score += 15.0
            reasons.append("RS momentum rising")
        elif momentum > 0.5:
            score += 8.0
        else:
            weaknesses.append("RS momentum muted")

        if new_high:
            score += 15.0
            reasons.append("RS making new highs")
        else:
            weaknesses.append("RS not yet at fresh highs")

        if leadership:
            score += 10.0
            reasons.append("RS leadership within sector")
        else:
            weaknesses.append("Sector leadership not confirmed")

        if trend_slope > 0:
            score += 10.0
        else:
            weaknesses.append("RS trend slope negative")

        metrics = {
            "current_rs_proxy": round(current, 2),
            "slope_3d": round(slope_3d, 2),
            "slope_5d": round(slope_5d, 2),
            "slope_10d": round(slope_10d, 2),
            "acceleration": round(accel, 2),
            "trend_slope": round(trend_slope, 4),
            "momentum_pct": round(momentum, 2),
            "new_high": new_high,
            "leadership": leadership,
        }
        final_score = round(min(score, 100.0), 2)
        return TransitionGateResult(
            self.name,
            final_score,
            final_score >= context.config.transition_min_rs_acceleration_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
