"""Shared result-label helpers for scanner modes."""

from __future__ import annotations

from typing import List


def build_reason_label(reasons: List[str]) -> str:
    return ", ".join(reasons) if reasons else "No clear signal"


def build_reason_text(reasons: List[str], score: float) -> str:
    lines = [f"Score: {score:.1f}"]
    if reasons:
        lines.append("Reasons:")
        lines.extend(f"✔ {reason}" for reason in reasons)
    return "\n".join(lines)


def trade_quality(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "Reject"


def setup_id(score: float, reasons: List[str]) -> str:
    setup_ids = []
    if any("Price above 200 EMA" in reason or "EMA alignment" in reason for reason in reasons):
        setup_ids.append("S1 Early Accumulation")
    if any("Tight base range" in reason or "Consolidation building" in reason for reason in reasons):
        setup_ids.append("S2 Tight Base")
    if any("ATR contracting" in reason or "Bollinger width contracting" in reason for reason in reasons):
        setup_ids.append("S3 VCP")
    if any("Breakout confirmed" in reason for reason in reasons):
        setup_ids.append("S5 Breakout")
    if any("Breakout volume strong" in reason for reason in reasons):
        setup_ids.append("S6 Breakout Retest")
    if not setup_ids:
        return "S9 Trend Continuation"
    return " + ".join(setup_ids[:2])


def recommendation(score: float, reasons: List[str]) -> str:
    if score >= 90:
        return "Buy"
    if score >= 80:
        return "Watch Closely"
    if score >= 75:
        return "Watch"
    return "Reject"


def confidence(score: float) -> str:
    if score >= 90:
        return "Very High"
    if score >= 80:
        return "High"
    if score >= 75:
        return "Medium"
    return "Low"
