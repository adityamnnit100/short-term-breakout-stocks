"""Price acceptance gate."""

from __future__ import annotations

from typing import List

import numpy as np

from .models import TransitionContext, TransitionGate, TransitionGateResult


class PriceAcceptanceGate(TransitionGate):
    name = "price_acceptance"

    def evaluate(self, context: TransitionContext) -> TransitionGateResult:
        frame = context.frame.tail(max(context.config.transition_history_window + 10, 20)).copy()
        if frame.empty or not {"Open", "High", "Low", "Close"}.issubset(frame.columns):
            return TransitionGateResult(self.name, 0.0, False, weaknesses=["Missing OHLC history"], metrics={"reason": "missing_ohlc"})

        high = frame["High"].astype(float)
        low = frame["Low"].astype(float)
        close = frame["Close"].astype(float)
        open_ = frame["Open"].astype(float)

        range_ = (high - low).replace(0, np.nan)
        close_location = ((close - low) / range_).replace([np.inf, -np.inf], np.nan).dropna()
        body_ratio = ((close - open_).abs() / range_).replace([np.inf, -np.inf], np.nan).dropna()
        downside = (close.diff().fillna(0) < 0).astype(float)
        downside_volatility = float(close.diff().tail(min(len(close), 10)).std() or 0.0)
        gap_retention = int(sum((open_.iloc[i] > close.iloc[i - 1]) and (close.iloc[i] >= open_.iloc[i]) for i in range(1, len(frame))))
        higher_lows = bool(low.tail(5).dropna().is_monotonic_increasing)
        tight_closes = bool(close_location.tail(5).mean() >= 0.7 if not close_location.tail(5).empty else False)
        small_bodies = bool(body_ratio.tail(5).mean() <= 0.35 if not body_ratio.tail(5).empty else False)
        strong_close_pct = float(close_location.tail(min(len(close_location), 5)).mean() * 100.0) if not close_location.empty else 0.0
        near_high_count = int(sum(float(value) >= 0.8 for value in close_location.tail(10).tolist()))
        reduced_downside = bool(downside_volatility <= float(close.tail(10).std() or 0.0))

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []

        if strong_close_pct >= 80:
            score += 25.0
            reasons.append("Closing near highs")
        elif strong_close_pct >= 65:
            score += 15.0
        else:
            weaknesses.append("Closes not near highs")

        if reduced_downside:
            score += 15.0
            reasons.append("Reduced downside volatility")
        else:
            weaknesses.append("Downside volatility still elevated")

        if higher_lows:
            score += 20.0
            reasons.append("Higher low sequence")
        else:
            weaknesses.append("Higher lows not yet established")

        if small_bodies:
            score += 15.0
            reasons.append("Small-bodied candles near highs")
        else:
            weaknesses.append("Candles too wide")

        if gap_retention >= 2:
            score += 15.0
            reasons.append("Gap retention constructive")
        elif gap_retention == 1:
            score += 8.0

        if near_high_count >= 3:
            score += 10.0
            reasons.append("Acceptance near highs")
        elif near_high_count >= 1:
            score += 5.0

        if tight_closes:
            score += 10.0
            reasons.append("Tight closes")
        else:
            weaknesses.append("Closes not tight enough")

        metrics = {
            "strong_close_pct": round(strong_close_pct, 2),
            "downside_volatility": round(downside_volatility, 4),
            "gap_retention": gap_retention,
            "higher_lows": higher_lows,
            "small_bodies": small_bodies,
            "near_high_count": near_high_count,
            "tight_closes": tight_closes,
        }
        final_score = round(min(score, 100.0), 2)
        return TransitionGateResult(
            self.name,
            final_score,
            final_score >= context.config.transition_min_price_acceptance_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
