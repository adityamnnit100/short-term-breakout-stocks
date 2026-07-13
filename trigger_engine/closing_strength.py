"""Closing strength trigger module."""

from __future__ import annotations

from typing import List

from .models import TriggerContext, TriggerModule, TriggerModuleResult


class ClosingStrengthModule(TriggerModule):
    name = "closing_strength"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        cfg = context.config
        frame = context.frame.tail(10).copy()
        if frame.empty:
            return TriggerModuleResult(self.name, False, weaknesses=["Missing daily history"], metrics={"reason": "missing_history"})

        close = frame["Close"].astype(float)
        high = frame["High"].astype(float)
        low = frame["Low"].astype(float)
        open_ = frame["Open"].astype(float)
        current_close = float(close.iloc[-1])
        current_high = float(high.iloc[-1])
        current_low = float(low.iloc[-1])
        current_open = float(open_.iloc[-1])
        day_range = max(current_high - current_low, 1e-9)
        close_location = (current_close - current_low) / day_range
        strong_finish = current_close >= current_open
        higher_closes = bool(close.tail(5).is_monotonic_increasing)
        body_strength = abs(current_close - current_open) / day_range

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []
        if close_location >= cfg.trigger_close_strength_min:
            score += 45.0
            reasons.append("Strong finish near highs")
        else:
            weaknesses.append("Close location weak")
        if strong_finish:
            score += 25.0
            reasons.append("Closed above open")
        else:
            weaknesses.append("No strong finish")
        if higher_closes:
            score += 20.0
            reasons.append("Higher closes intact")
        else:
            weaknesses.append("Higher closes absent")
        if body_strength <= 0.5:
            score += 10.0
            reasons.append("Candle body acceptable")
        else:
            weaknesses.append("Candle body too stretched")

        metrics = {
            "close_location": round(close_location, 2),
            "strong_finish": strong_finish,
            "higher_closes": higher_closes,
            "body_strength": round(body_strength, 2),
        }
        final_score = round(min(score, 100.0), 2)
        return TriggerModuleResult(
            self.name,
            passed=close_location >= cfg.trigger_close_strength_min and strong_finish and higher_closes,
            score=final_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
