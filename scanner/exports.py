"""Output helpers for scanner result persistence."""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from .config import ScannerConfig
from .report import save_results


WATCHLIST_EXPORT_RENAMES = {
    "ticker": "Ticker",
    "score": "Watchlist Score",
    "sector": "Sector",
    "trend": "Trend",
    "base_score": "Base Score",
    "volume_score": "Volume Score",
    "relative_strength": "Relative Strength",
    "atr_contraction": "ATR Contraction",
    "days_in_consolidation": "Days in Consolidation",
    "trade_quality": "Trade Quality",
    "setup_id": "Setup ID",
    "recommendation": "Recommendation",
    "confidence": "Confidence",
    "reason_text": "Reason Text",
    "setup_score": "Setup Score",
    "setup_category": "Setup Category",
    "setup_base_score": "Setup Base Score",
    "setup_compression_score": "Setup Compression Score",
    "setup_volume_score": "Setup Volume Score",
    "setup_resistance_score": "Setup Resistance Score",
    "setup_structure_score": "Setup Structure Score",
    "setup_risk_score": "Setup Risk Score",
    "setup_reasons": "Setup Reasons",
    "setup_weaknesses": "Setup Weaknesses",
    "setup_qualifies": "Setup Qualifies",
    "transition_score": "Transition Score",
    "transition_category": "Transition Category",
    "transition_setup_velocity_score": "Transition Setup Velocity Score",
    "transition_rs_acceleration_score": "Transition RS Acceleration Score",
    "transition_volume_transition_score": "Transition Volume Score",
    "transition_compression_evolution_score": "Transition Compression Score",
    "transition_resistance_pressure_score": "Transition Resistance Score",
    "transition_price_acceptance_score": "Transition Price Acceptance Score",
    "transition_opportunity_velocity_score": "Transition Opportunity Velocity Score",
    "transition_reasons": "Transition Reasons",
    "transition_weaknesses": "Transition Weaknesses",
    "transition_qualifies": "Transition Qualifies",
    "trigger_decision": "Trigger Decision",
    "trigger_confidence": "Trigger Confidence",
    "trigger_score": "Trigger Score",
    "trigger_priority_score": "Trigger Priority Score",
    "trigger_rank_percentile": "Trigger Rank Percentile",
    "trigger_qualifies": "Trigger Qualifies",
    "trigger_hard_gate_failures": "Trigger Hard Gate Failures",
    "trigger_reasons": "Trigger Reasons",
    "trigger_weaknesses": "Trigger Weaknesses",
    "trigger_passed_modules": "Trigger Passed Modules",
    "trigger_failed_modules": "Trigger Failed Modules",
}

ENTRY_EXPORT_RENAMES = {
    "ticker": "Ticker",
    "score": "Entry Score",
    "sector": "Sector",
    "entry_price": "Entry Price",
    "stop_loss": "Stop Loss",
    "risk_pct": "Risk %",
    "target_1": "Target 1",
    "target_2": "Target 2",
    "risk_reward": "Risk Reward",
    "breakout_date": "Breakout Date",
    "breakout_volume_ratio": "Breakout Volume Ratio",
    "trade_quality": "Trade Quality",
    "setup_id": "Setup ID",
    "recommendation": "Recommendation",
    "confidence": "Confidence",
    "reason_text": "Reason Text",
    "setup_score": "Setup Score",
    "setup_category": "Setup Category",
    "setup_base_score": "Setup Base Score",
    "setup_compression_score": "Setup Compression Score",
    "setup_volume_score": "Setup Volume Score",
    "setup_resistance_score": "Setup Resistance Score",
    "setup_structure_score": "Setup Structure Score",
    "setup_risk_score": "Setup Risk Score",
    "setup_reasons": "Setup Reasons",
    "setup_weaknesses": "Setup Weaknesses",
    "setup_qualifies": "Setup Qualifies",
    "transition_score": "Transition Score",
    "transition_category": "Transition Category",
    "transition_setup_velocity_score": "Transition Setup Velocity Score",
    "transition_rs_acceleration_score": "Transition RS Acceleration Score",
    "transition_volume_transition_score": "Transition Volume Score",
    "transition_compression_evolution_score": "Transition Compression Score",
    "transition_resistance_pressure_score": "Transition Resistance Score",
    "transition_price_acceptance_score": "Transition Price Acceptance Score",
    "transition_opportunity_velocity_score": "Transition Opportunity Velocity Score",
    "transition_reasons": "Transition Reasons",
    "transition_weaknesses": "Transition Weaknesses",
    "transition_qualifies": "Transition Qualifies",
    "trigger_decision": "Trigger Decision",
    "trigger_confidence": "Trigger Confidence",
    "trigger_score": "Trigger Score",
    "trigger_priority_score": "Trigger Priority Score",
    "trigger_rank_percentile": "Trigger Rank Percentile",
    "trigger_qualifies": "Trigger Qualifies",
    "trigger_hard_gate_failures": "Trigger Hard Gate Failures",
    "trigger_reasons": "Trigger Reasons",
    "trigger_weaknesses": "Trigger Weaknesses",
    "trigger_passed_modules": "Trigger Passed Modules",
    "trigger_failed_modules": "Trigger Failed Modules",
}


def _export_path(output_path: Optional[str], suffix: str, default_path: str) -> str:
    return output_path.replace(".csv", suffix) if output_path else default_path


def _rejected_rows(results: pd.DataFrame, score_column: str, threshold: float, reason: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    if results is None or results.empty or score_column not in results.columns:
        return rows
    for _, row in results.iterrows():
        score = float(row.get(score_column, 0) or 0)
        if threshold * 0.9 <= score < threshold:
            rows.append({
                "Ticker": row.get("Ticker"),
                "Score": score,
                "Missing Criteria": reason,
            })
    return rows


def build_rejected_rows(
    watch_results: pd.DataFrame,
    entry_results: pd.DataFrame,
    config: ScannerConfig,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    rows.extend(_rejected_rows(watch_results, "Watchlist Score", config.watchlist_min_score, "Watchlist threshold near miss"))
    rows.extend(_rejected_rows(entry_results, "Entry Score", config.entry_min_score, "Entry threshold near miss"))
    return rows


def export_scan_results(
    watch_results: pd.DataFrame,
    entry_results: pd.DataFrame,
    config: ScannerConfig,
    output_path: Optional[str] = None,
) -> None:
    if watch_results is not None and not watch_results.empty:
        watch_path = _export_path(output_path, "_watchlist.csv", "data/watchlist.csv")
        watchlist_cols = list(WATCHLIST_EXPORT_RENAMES.values())
        output_watchlist_cols = [col for col in watchlist_cols if col in watch_results.columns]
        save_results(watch_results, watch_path, columns=output_watchlist_cols)

    if entry_results is not None and not entry_results.empty:
        entry_path = _export_path(output_path, "_entry.csv", "data/entry.csv")
        entry_cols = list(ENTRY_EXPORT_RENAMES.values())
        output_entry_cols = [col for col in entry_cols if col in entry_results.columns]
        save_results(entry_results, entry_path, columns=output_entry_cols)

    near_misses = build_rejected_rows(watch_results, entry_results, config)
    if near_misses:
        rejected_path = _export_path(output_path, "_rejected.csv", "data/rejected.csv")
        save_results(pd.DataFrame(near_misses), rejected_path)
