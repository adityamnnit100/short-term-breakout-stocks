"""Trigger engine orchestrator."""

from __future__ import annotations

import logging
from datetime import datetime
from dataclasses import replace
from typing import Callable, Iterable, List, Optional

import pandas as pd

from quality_filter.models import QualityContext
from scanner.config import ScannerConfig
from setup_engine.models import SetupResult
from transition_engine.models import TransitionResult

from .breakout_confirmation import BreakoutConfirmationModule
from .closing_strength import ClosingStrengthModule
from .intraday_confirmation import IntradayConfirmationModule
from .models import TriggerContext, TriggerModule, TriggerModuleResult, TriggerResult
from .pocket_pivot import PocketPivotModule
from .relative_volume import RelativeVolumeModule
from .rs_confirmation import RSConfirmationModule
from .volume_confirmation import VolumeConfirmationModule

logger = logging.getLogger("AlphaScanner.Trigger")

IntradayLoader = Callable[[str], Optional[pd.DataFrame]]
HistoryLoader = Callable[[str, str, int], Iterable[dict]]
CandidateRow = dict


def _default_history_loader(ticker: str, scan_mode: str, limit: int) -> List[dict]:
    try:
        from alphascanner_ui.database import execute_query
    except Exception:
        return []

    rows = execute_query(
        """
        SELECT analysis_date, scan_mode, trigger_decision, trigger_confidence
        FROM trigger_analyses
        WHERE ticker = ? AND scan_mode = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (ticker, scan_mode, limit),
        is_select=True,
    )
    return [dict(row) for row in reversed(rows)] if rows else []


class TriggerEngine:
    """Pure timing engine that decides whether today is the entry day."""

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        modules: Optional[Iterable[TriggerModule]] = None,
        intraday_loader: Optional[IntradayLoader] = None,
        history_loader: Optional[HistoryLoader] = None,
    ):
        self.config = config or ScannerConfig()
        self.intraday_loader = intraday_loader
        self.history_loader = history_loader or _default_history_loader
        self.modules: List[TriggerModule] = list(modules) if modules is not None else [
            PocketPivotModule(),
            RelativeVolumeModule(),
            BreakoutConfirmationModule(),
            ClosingStrengthModule(),
            RSConfirmationModule(),
            VolumeConfirmationModule(),
            IntradayConfirmationModule(),
        ]

    def build_context(
        self,
        quality_context: QualityContext,
        setup_result: SetupResult,
        transition_result: TransitionResult,
        scan_mode: str = "Entry",
    ) -> TriggerContext:
        intraday_frame = None
        if self.intraday_loader is not None:
            try:
                intraday_frame = self.intraday_loader(quality_context.ticker)
            except Exception as exc:
                logger.warning("Intraday lookup failed for %s: %s", quality_context.ticker, exc)

        context = TriggerContext(
            ticker=quality_context.ticker,
            scan_mode=scan_mode,
            config=self.config,
            quality=quality_context,
            setup=setup_result,
            transition=transition_result,
            frame=quality_context.frame,
            intraday_frame=intraday_frame,
        )

        if self.history_loader is not None:
            try:
                history_rows = list(self.history_loader(quality_context.ticker, scan_mode, self.config.transition_history_window))
                context.trigger_notes["history"] = history_rows
            except Exception as exc:
                logger.warning("Trigger history lookup failed for %s: %s", quality_context.ticker, exc)

        return context

    @staticmethod
    def _confidence_from_score(module_count: int, pass_count: int, decision: str, critical_pass: bool) -> str:
        if decision == "BUY" and critical_pass and pass_count == module_count:
            return "Very High"
        if decision == "BUY" and pass_count >= max(module_count - 1, 1):
            return "High"
        if decision in {"BUY", "WATCH"} and pass_count >= max(module_count // 2, 1):
            return "Medium"
        return "Low"

    def _module_payload(self, result) -> dict:
        return {
            "passed": result.passed,
            "score": result.score,
            "reasons": list(result.reasons),
            "weaknesses": list(result.weaknesses),
            "metrics": dict(result.metrics),
        }

    def _priority_score_from_module_map(self, module_map: dict, setup_score: float, transition_score: float) -> float:
        weights = {
            "pocket_pivot": 0.10,
            "relative_volume": 0.20,
            "breakout_confirmation": 0.25,
            "closing_strength": 0.15,
            "rs_confirmation": 0.15,
            "volume_confirmation": 0.15,
        }
        weighted_trigger = 0.0
        weight_total = 0.0
        for name, weight in weights.items():
            result = module_map.get(name)
            if result is None:
                continue
            weighted_trigger += float(result.score or 0.0) * weight
            weight_total += weight
        trigger_component = weighted_trigger / weight_total if weight_total > 0 else 0.0
        return round(
            min(
                trigger_component * 0.55
                + float(transition_score or 0.0) * 0.25
                + float(setup_score or 0.0) * 0.20,
                100.0,
            ),
            2,
        )

    def _hard_gate_status(self, context: TriggerContext, module_map: dict) -> tuple[list[str], list[str], list[str]]:
        passed: List[str] = []
        critical_failures: List[str] = []
        soft_failures: List[str] = []

        setup_ok = context.setup.setup_score >= self.config.trigger_min_setup_score
        transition_ok = context.transition.transition_score >= self.config.trigger_min_transition_score
        market_regime = str(context.quality.market_regime or "UNKNOWN").upper()
        sector_strength = float(getattr(context.quality, "sector_strength", 0.0) or 0.0)
        market_regime_score = float(getattr(context.quality, "market_regime_score", 0.0) or 0.0)

        if market_regime in {"BEARISH", "STRONG BEAR"}:
            market_tape_ok = False
        elif market_regime == "CAUTION" and (sector_strength < 5.0 or market_regime_score < 0.0):
            market_tape_ok = False
        elif market_regime == "NEUTRAL" and sector_strength < 4.0 and market_regime_score < 0.2:
            market_tape_ok = False
        else:
            market_tape_ok = True

        critical_checks = [
            ("setup_score", setup_ok, f"Setup score below {self.config.trigger_min_setup_score:.0f}"),
            ("transition_score", transition_ok, f"Transition score below {self.config.trigger_min_transition_score:.0f}"),
            ("market_tape", market_tape_ok, f"Weak market tape: {market_regime.lower()}"),
            ("breakout_confirmation", module_map.get("breakout_confirmation").passed if module_map.get("breakout_confirmation") else False, "Breakout confirmation failed"),
            ("relative_volume", module_map.get("relative_volume").passed if module_map.get("relative_volume") else False, "Relative volume confirmation failed"),
            ("closing_strength", module_map.get("closing_strength").passed if module_map.get("closing_strength") else False, "Closing strength failed"),
        ]
        soft_checks = [
            ("pocket_pivot", module_map.get("pocket_pivot").passed if module_map.get("pocket_pivot") else False, "Pocket pivot failed"),
            ("rs_confirmation", module_map.get("rs_confirmation").passed if module_map.get("rs_confirmation") else False, "Relative strength confirmation failed"),
            ("volume_confirmation", module_map.get("volume_confirmation").passed if module_map.get("volume_confirmation") else False, "Volume confirmation failed"),
        ]
        if self.config.trigger_enable_intraday_confirmation:
            soft_checks.append(
                (
                    "intraday_confirmation",
                    module_map.get("intraday_confirmation").passed if module_map.get("intraday_confirmation") else False,
                    "Intraday confirmation failed",
                )
            )

        for name, ok, failure in critical_checks:
            if ok:
                passed.append(name)
            else:
                critical_failures.append(failure)
        for name, ok, failure in soft_checks:
            if ok:
                passed.append(name)
            else:
                soft_failures.append(failure)

        return passed, critical_failures, soft_failures

    def _category_from_rank(self, rank_percentile: float, critical_failures: List[str], soft_failures: List[str]) -> str:
        if critical_failures:
            return "WAIT"
        if not soft_failures:
            if rank_percentile <= self.config.trigger_buy_now_top_percentile:
                return "BUY NOW"
            if rank_percentile <= self.config.trigger_early_buy_top_percentile:
                return "EARLY BUY"
            if rank_percentile <= self.config.trigger_watch_top_percentile:
                return "WATCH"
            return "WAIT"
        if len(soft_failures) <= self.config.trigger_early_buy_soft_miss_max:
            if rank_percentile <= self.config.trigger_early_buy_top_percentile:
                return "EARLY BUY"
            if rank_percentile <= self.config.trigger_watch_top_percentile:
                return "WATCH"
        if rank_percentile <= self.config.trigger_watch_top_percentile:
            return "WATCH"
        return "WAIT"

    def _confidence_from_category(self, decision: str, rank_percentile: float, soft_failures: List[str]) -> str:
        if decision == "BUY NOW" and rank_percentile <= self.config.trigger_buy_now_top_percentile:
            return "Very High"
        if decision == "EARLY BUY" and rank_percentile <= self.config.trigger_early_buy_top_percentile:
            return "High"
        if decision == "WATCH" and rank_percentile <= self.config.trigger_watch_top_percentile and len(soft_failures) <= 1:
            return "Medium"
        return "Low"

    def evaluate(self, context: TriggerContext) -> TriggerResult:
        if not self.config.trigger_engine_enabled:
            return TriggerResult(
                analysis_date=datetime.now().strftime("%Y-%m-%d"),
                ticker=context.ticker,
                scan_mode=context.scan_mode,
                decision="WAIT",
                confidence="Low",
                qualifies=False,
                trigger_score=0.0,
                priority_score=0.0,
                reasons=["Trigger engine disabled"],
                weaknesses=[],
                module_results={"trigger_engine": {"disabled": True}},
                metrics={"trigger_engine": "disabled"},
            )

        module_results: List[TriggerModuleResult] = []
        module_map = {}
        passed_modules: List[str] = []
        failed_modules: List[str] = []
        reasons: List[str] = []
        weaknesses: List[str] = []

        for module in self.modules:
            result = module.evaluate(context)
            module_results.append(result)
            module_map[module.name] = result
            context.trigger_notes[module.name] = result.metrics
            if result.passed:
                passed_modules.append(module.name)
                reasons.extend(result.reasons)
            else:
                failed_modules.append(module.name)
                weaknesses.extend(result.weaknesses)

        module_count = len(module_results)
        pass_count = len(passed_modules)
        hard_gate_passed, critical_failures, soft_failures = self._hard_gate_status(context, module_map)
        priority_score = self._priority_score_from_module_map(module_map, context.setup.setup_score, context.transition.transition_score)
        rank_percentile = round(max(1.0, 100.0 - priority_score), 2)

        if critical_failures:
            decision = "WAIT"
        elif not soft_failures:
            if priority_score >= self.config.trigger_min_trigger_score + 12.0 and rank_percentile <= self.config.trigger_buy_now_top_percentile:
                decision = "BUY NOW"
            elif priority_score >= self.config.trigger_min_trigger_score + 7.0 and rank_percentile <= self.config.trigger_early_buy_top_percentile:
                decision = "EARLY BUY"
            elif priority_score >= self.config.trigger_min_trigger_score and rank_percentile <= self.config.trigger_watch_top_percentile:
                decision = "WATCH"
            else:
                decision = "WAIT"
        elif len(soft_failures) <= self.config.trigger_early_buy_soft_miss_max:
            if priority_score >= self.config.trigger_min_trigger_score + 4.0 and rank_percentile <= self.config.trigger_early_buy_top_percentile:
                decision = "EARLY BUY"
            elif priority_score >= self.config.trigger_min_trigger_score and rank_percentile <= self.config.trigger_watch_top_percentile:
                decision = "WATCH"
            else:
                decision = "WAIT"
        else:
            decision = "WATCH" if priority_score >= self.config.trigger_min_trigger_score and rank_percentile <= self.config.trigger_watch_top_percentile else "WAIT"

        confidence = self._confidence_from_category(decision, rank_percentile, soft_failures)
        qualifies = decision in {"BUY NOW", "EARLY BUY"}

        module_payload = {result.name: self._module_payload(result) for result in module_results}
        trigger_score = round(priority_score, 2)

        return TriggerResult(
            analysis_date=datetime.now().strftime("%Y-%m-%d"),
            ticker=context.ticker,
            scan_mode=context.scan_mode,
            decision=decision,
            confidence=confidence,
            qualifies=qualifies,
            trigger_score=trigger_score,
            priority_score=priority_score,
            rank_percentile=rank_percentile,
            hard_gate_failures=critical_failures + soft_failures,
            hard_gate_passed=hard_gate_passed,
            passed_modules=passed_modules,
            failed_modules=failed_modules,
            reasons=reasons,
            weaknesses=weaknesses,
            module_results=module_payload,
            metrics={result.name: result.metrics for result in module_results},
        )

    def rank_candidate_rows(self, rows: List[CandidateRow]) -> List[CandidateRow]:
        if not rows:
            return []

        ranked: List[tuple[float, CandidateRow, List[str], List[str]]] = []
        for row in rows:
            module_results = row.get("trigger_module_results", {}) or {}
            setup_score = float(row.get("setup_score", row.get("Setup Score", 0.0)) or 0.0)
            transition_score = float(row.get("transition_score", row.get("Transition Score", 0.0)) or 0.0)
            priority_score = self._row_priority_score(row, module_results, setup_score, transition_score)
            critical_failures, soft_failures = self._row_gate_failures(row, module_results)
            ranked.append((priority_score, row, critical_failures, soft_failures))

        ranked.sort(key=lambda item: item[0], reverse=True)
        total = len(ranked)
        final_rows: List[CandidateRow] = []
        for index, (priority_score, row, critical_failures, soft_failures) in enumerate(ranked):
            # Use the same score->percentile mapping as per-ticker evaluation for consistency.
            # This mirrors `evaluate()` which computes `rank_percentile = 100.0 - priority_score`.
            rank_percentile = round(max(1.0, 100.0 - float(priority_score or 0.0)), 2)
            decision = self._category_from_rank(rank_percentile, critical_failures, soft_failures)
            confidence = self._confidence_from_category(decision, rank_percentile, soft_failures)
            final_row = dict(row)
            final_row["trigger_priority_score"] = round(priority_score, 2)
            final_row["trigger_rank_percentile"] = rank_percentile
            final_row["trigger_decision"] = decision
            final_row["trigger_confidence"] = confidence
            final_row["trigger_qualifies"] = decision in {"BUY NOW", "EARLY BUY"}
            final_row["passed"] = bool(row.get("passed", True)) and final_row["trigger_qualifies"]
            final_row["trigger_hard_gate_failures"] = critical_failures + soft_failures
            if self.config.trigger_calibration_mode:
                final_row["trigger_calibration"] = {
                    "universe_size": total,
                    "percentile": rank_percentile,
                    "priority_score": round(priority_score, 2),
                    "decision": decision,
                }
            final_rows.append(final_row)
        return final_rows

    def _row_priority_score(
        self,
        row: CandidateRow,
        module_results: dict,
        setup_score: float,
        transition_score: float,
    ) -> float:
        weights = {
            "pocket_pivot": 0.10,
            "relative_volume": 0.20,
            "breakout_confirmation": 0.25,
            "closing_strength": 0.15,
            "rs_confirmation": 0.15,
            "volume_confirmation": 0.15,
        }
        weighted_trigger = 0.0
        weight_total = 0.0
        for name, weight in weights.items():
            payload = module_results.get(name, {}) or {}
            weighted_trigger += float(payload.get("score", 0.0) or 0.0) * weight
            weight_total += weight
        trigger_component = weighted_trigger / weight_total if weight_total > 0 else 0.0
        return round(
            min(trigger_component * 0.55 + transition_score * 0.25 + setup_score * 0.20, 100.0),
            2,
        )

    def _row_gate_failures(self, row: CandidateRow, module_results: dict) -> tuple[List[str], List[str]]:
        setup_score = float(row.get("setup_score", row.get("Setup Score", 0.0)) or 0.0)
        transition_score = float(row.get("transition_score", row.get("Transition Score", 0.0)) or 0.0)
        market_regime = str(row.get("quality_market_regime", row.get("market_regime", "UNKNOWN")) or "UNKNOWN").upper()

        critical_failures: List[str] = []
        soft_failures: List[str] = []

        if setup_score < self.config.trigger_min_setup_score:
            critical_failures.append("Setup score below threshold")
        if transition_score < self.config.trigger_min_transition_score:
            critical_failures.append("Transition score below threshold")
        if market_regime in {"BEARISH", "STRONG BEAR"}:
            critical_failures.append("Market regime bearish")

        module_checks = {
            "breakout_confirmation": ("Breakout confirmation failed", critical_failures),
            "relative_volume": ("Relative volume confirmation failed", critical_failures),
            "closing_strength": ("Closing strength failed", critical_failures),
            "pocket_pivot": ("Pocket pivot failed", soft_failures),
            "rs_confirmation": ("Relative strength confirmation failed", soft_failures),
            "volume_confirmation": ("Volume confirmation failed", soft_failures),
        }
        if self.config.trigger_enable_intraday_confirmation:
            module_checks["intraday_confirmation"] = ("Intraday confirmation failed", soft_failures)

        for module_name, (message, bucket) in module_checks.items():
            payload = module_results.get(module_name, {})
            if not payload:
                bucket.append(message)
                continue
            if not bool(payload.get("passed")):
                bucket.append(message)

        return critical_failures, soft_failures
