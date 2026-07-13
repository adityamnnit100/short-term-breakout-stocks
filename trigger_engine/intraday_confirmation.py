"""Optional intraday confirmation module."""

from __future__ import annotations

from typing import List

import pandas as pd

from .models import TriggerContext, TriggerModule, TriggerModuleResult


class IntradayConfirmationModule(TriggerModule):
    name = "intraday_confirmation"

    def evaluate(self, context: TriggerContext) -> TriggerModuleResult:
        if not context.config.trigger_enable_intraday_confirmation:
            return TriggerModuleResult(self.name, True, score=0.0, reasons=["Intraday confirmation disabled"], metrics={"skipped": True})

        frame = context.intraday_frame
        if frame is None or frame.empty:
            return TriggerModuleResult(self.name, True, score=0.0, reasons=["Intraday data unavailable"], metrics={"skipped": True})

        data = frame.copy()
        for column in ["Open", "High", "Low", "Close", "Volume"]:
            if column not in data.columns:
                return TriggerModuleResult(self.name, False, weaknesses=["Incomplete intraday data"], metrics={"reason": "incomplete_intraday"})
            data[column] = pd.to_numeric(data[column], errors="coerce")
        data = data.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        if data.empty:
            return TriggerModuleResult(self.name, False, weaknesses=["No usable intraday bars"], metrics={"reason": "empty_intraday"})

        latest = data.iloc[-1]
        session_high = float(data["High"].max())
        session_low = float(data["Low"].min())
        session_close = float(latest["Close"])
        session_open = float(data.iloc[0]["Open"])
        vwap = float((data["Close"] * data["Volume"]).sum() / max(float(data["Volume"].sum()), 1e-9))
        intraday_rvol = float(data["Volume"].iloc[-1] / max(float(data["Volume"].tail(min(len(data), 20)).mean()), 1e-9))
        near_high = session_close >= session_high * context.config.trigger_intraday_high_hold_min
        above_vwap = session_close >= vwap or session_close >= session_open
        held_vwap = session_close >= max(vwap, session_open)

        score = 0.0
        reasons: List[str] = []
        weaknesses: List[str] = []
        if above_vwap:
            score += 35.0
            reasons.append("Holding VWAP")
        else:
            weaknesses.append("Below VWAP")
        if near_high:
            score += 35.0
            reasons.append("Price near day's high")
        else:
            weaknesses.append("Not near high")
        if intraday_rvol >= context.config.trigger_intraday_rvol_min:
            score += 30.0
            reasons.append("Intraday RVOL strong")
        else:
            weaknesses.append("Intraday RVOL weak")

        metrics = {
            "session_high": round(session_high, 2),
            "session_low": round(session_low, 2),
            "session_close": round(session_close, 2),
            "vwap": round(vwap, 2),
            "intraday_rvol": round(intraday_rvol, 2),
            "near_high": near_high,
            "above_vwap": above_vwap,
            "held_vwap": held_vwap,
        }
        final_score = round(min(score, 100.0), 2)
        return TriggerModuleResult(
            self.name,
            passed=above_vwap and near_high and intraday_rvol >= context.config.trigger_intraday_rvol_min,
            score=final_score,
            reasons=reasons,
            weaknesses=weaknesses,
            metrics=metrics,
        )
