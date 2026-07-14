"""Diagnostics helpers for scanner pipeline instrumentation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Mapping, Optional, TYPE_CHECKING


@dataclass(frozen=True)
class DiagnosticsRuleHit:
    rule: str
    actual: Any = None
    required: Any = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiagnosticsRejection:
    ticker: str
    stage: str
    failed_rules: List[DiagnosticsRuleHit] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "stage": self.stage,
            "failed_rules": [
                {"rule": rule.rule, "actual": rule.actual, "required": rule.required, "metrics": rule.metrics}
                for rule in self.failed_rules
            ],
            "metrics": self.metrics,
        }


if TYPE_CHECKING:
    from .config import ScannerConfig


class DiagnosticsCollector:
    """Thread-safe collector for scan-stage pass/fail instrumentation."""

    def __init__(self, config: Optional["ScannerConfig"] = None, enabled: bool = False, top_rules: int = 3):
        self.enabled = enabled
        self.config = config
        self.top_rules = max(1, int(top_rules or 3))
        self._lock = Lock()
        self.universe_size = 0
        self.stage_counts: Dict[str, Dict[str, int]] = {
            "quality": {"passed": 0, "rejected": 0},
            "setup": {"passed": 0, "rejected": 0},
            "transition": {"passed": 0, "rejected": 0},
            "trigger": {"passed": 0, "rejected": 0},
        }
        self.trigger_module_counts: Dict[str, Dict[str, int]] = {}
        self.decision_counts: Counter[str] = Counter()
        self.rule_rejection_counts: Counter[str] = Counter()
        self.rejections: List[DiagnosticsRejection] = []
        self.thresholds = self._build_threshold_map()

    def record_universe(self, size: int) -> None:
        if not self.enabled:
            return
        with self._lock:
            self.universe_size = int(size)

    def _record_stage(self, stage: str, passed: bool) -> None:
        bucket = self.stage_counts.setdefault(stage, {"passed": 0, "rejected": 0})
        key = "passed" if passed else "rejected"
        bucket[key] = int(bucket.get(key, 0)) + 1

    def _add_rejection(self, ticker: str, stage: str, failed_rules: List[DiagnosticsRuleHit], metrics: Optional[Dict[str, Any]] = None) -> None:
        rejection = DiagnosticsRejection(ticker=ticker, stage=stage, failed_rules=failed_rules, metrics=metrics or {})
        self.rejections.append(rejection)
        for rule in failed_rules:
            self.rule_rejection_counts[rule.rule] += 1

    def _build_threshold_map(self) -> Dict[str, Dict[str, Any]]:
        if not self.config:
            return {}
        cfg = self.config
        return {
            "quality": {
                "Liquidity Too Low": cfg.quality_min_avg_volume,
                "Average Daily Turnover Too Low": cfg.quality_min_avg_turnover,
                "Trend Template Failed": True,
                "EMA Alignment Failed": True,
                "Higher Highs Failed": True,
                "Higher Lows Failed": True,
                "Relative Strength Below Threshold": cfg.quality_min_relative_strength,
                "Weak Sector": cfg.quality_min_sector_strength,
                "Market Cap Below Minimum": cfg.quality_min_market_cap_cr,
                "Market Cap Above Maximum": cfg.quality_max_market_cap_cr,
            },
            "setup": {
                "base_quality": cfg.setup_min_base_quality_score,
                "compression": cfg.setup_min_compression_score,
                "volume_dryup": cfg.setup_min_volume_score,
                "resistance": cfg.setup_min_resistance_score,
                "structure": cfg.setup_min_structure_score,
                "risk": cfg.setup_min_risk_score,
            },
            "transition": {
                "setup_velocity": cfg.transition_min_setup_velocity_score,
                "rs_acceleration": cfg.transition_min_rs_acceleration_score,
                "volume_transition": cfg.transition_min_volume_transition_score,
                "compression_evolution": cfg.transition_min_compression_evolution_score,
                "resistance_pressure": cfg.transition_min_resistance_pressure_score,
                "price_acceptance": cfg.transition_min_price_acceptance_score,
                "opportunity_velocity": cfg.transition_min_opportunity_velocity_score,
            },
            "trigger": {
                "breakout_confirmation": cfg.trigger_breakout_volume_ratio_min,
                "relative_volume": cfg.trigger_relative_volume_5d_min,
                "closing_strength": cfg.trigger_close_strength_min,
                "rs_confirmation": cfg.trigger_rs_proxy_min,
                "volume_confirmation": cfg.trigger_volume_transition_min,
                "pocket_pivot": cfg.trigger_pocket_pivot_volume_ratio,
            },
        }

    def _quality_failures(self, result: Mapping[str, Any]) -> List[DiagnosticsRuleHit]:
        details = result.get("quality_gate_results", {}) or {}
        failed = []
        for check in result.get("quality_failed_checks", []) or []:
            detail = {}
            if str(check) == "Liquidity Too Low":
                detail = details.get("liquidity", {}).get("detail", {})
                actual = detail.get("avg_volume")
            elif str(check) == "Average Daily Turnover Too Low":
                detail = details.get("liquidity", {}).get("detail", {})
                actual = detail.get("avg_turnover")
            elif str(check) in {"Trend Template Failed", "EMA Alignment Failed", "Higher Highs Failed", "Higher Lows Failed"}:
                detail = details.get("trend", {}).get("detail", {})
                actual = False
            elif str(check) == "Relative Strength Below Threshold":
                detail = details.get("relative_strength", {}).get("detail", {})
                actual = detail.get("relative_strength")
            elif str(check) == "Weak Sector":
                detail = details.get("sector", {}).get("detail", {})
                actual = detail.get("sector_strength")
            elif str(check) == "Market Cap Below Minimum":
                detail = details.get("market_cap", {}).get("detail", {})
                actual = detail.get("market_cap_cr")
            elif str(check) == "Market Cap Above Maximum":
                detail = details.get("market_cap", {}).get("detail", {})
                actual = detail.get("market_cap_cr")
            else:
                detail = dict(details.get("market_cap", {}).get("detail", {}) or {})
                actual = None
            required = self.thresholds.get("quality", {}).get(str(check))
            failed.append(DiagnosticsRuleHit(rule=str(check), actual=actual, required=required, metrics=dict(detail)))
        return failed

    def _stage_rule_hits(self, stage: str, gate_results: Mapping[str, Any]) -> List[DiagnosticsRuleHit]:
        hits: List[DiagnosticsRuleHit] = []
        threshold_map = self.thresholds.get(stage, {})
        for name, payload in gate_results.items():
            if payload.get("passed", False):
                continue
            metrics = dict(payload.get("metrics", {}) or {})
            actual = payload.get("score", 0.0)
            required = threshold_map.get(name)
            hits.append(DiagnosticsRuleHit(rule=name, actual=actual, required=required, metrics=metrics))
        return hits

    def _trigger_failures(self, result: Mapping[str, Any]) -> List[DiagnosticsRuleHit]:
        module_results = result.get("trigger_module_results", {}) or {}
        hits: List[DiagnosticsRuleHit] = []
        threshold_map = self.thresholds.get("trigger", {})
        for name, payload in module_results.items():
            if payload.get("passed", False):
                continue
            metrics = dict(payload.get("metrics", {}) or {})
            actual = payload.get("score", 0.0)
            required = threshold_map.get(name)
            hits.append(DiagnosticsRuleHit(rule=name, actual=actual, required=required, metrics=metrics))
        for hard_fail in result.get("trigger_hard_gate_failures", []) or []:
            hits.append(DiagnosticsRuleHit(rule=str(hard_fail), actual=None, required=None, metrics={}))
        return hits

    def record_result(self, result: Mapping[str, Any]) -> None:
        if not self.enabled or not result:
            return

        ticker = str(result.get("ticker") or result.get("Ticker") or "UNKNOWN")
        with self._lock:
            if "quality_passed" in result or "quality_failed_checks" in result:
                quality_passed = bool(result.get("quality_passed", True))
                self._record_stage("quality", quality_passed)
                if not quality_passed:
                    failures = self._quality_failures(result)
                    self._add_rejection(ticker, "Quality Filter", failures, dict(result.get("quality_details", {}) or {}))
                    return  # Stop processing if quality fails (funnel logic)

            if "setup_qualifies" in result or "setup_gate_results" in result:
                setup_passed = bool(result.get("setup_qualifies", False))
                self._record_stage("setup", setup_passed)
                if not setup_passed:
                    failures = self._stage_rule_hits("setup", result.get("setup_gate_results", {}) or {})
                    self._add_rejection(ticker, "Setup Engine", failures, dict(result.get("setup_metrics", {}) or {}))
                    # Do not return, allow other stages to be recorded for parallel analysis

            if "transition_qualifies" in result or "transition_gate_results" in result:
                transition_passed = bool(result.get("transition_qualifies", False))
                self._record_stage("transition", transition_passed)
                if not transition_passed:
                    failures = self._stage_rule_hits("transition", result.get("transition_gate_results", {}) or {})
                    self._add_rejection(ticker, "Transition Engine", failures, dict(result.get("transition_metrics", {}) or {}))
                    # Do not return

            if "trigger_decision" in result or "trigger_module_results" in result:
                decision = str(result.get("trigger_decision", "WAIT") or "WAIT")
                self.decision_counts[decision] += 1

                # The 'passed' flag from the scanner result determines if it's an actionable entry
                trigger_passed = bool(result.get("passed", False))
                self._record_stage("trigger", trigger_passed)

                # Record module-level pass/fail stats regardless of final decision
                module_results = result.get("trigger_module_results", {}) or {}
                for name, payload in module_results.items():
                    bucket = self.trigger_module_counts.setdefault(name, {"passed": 0, "failed": 0})
                    if payload.get("passed", False):
                        bucket["passed"] += 1
                    else:
                        bucket["failed"] += 1

                # A stock is "rejected" by the trigger engine if it's not a buy signal
                if decision not in {"BUY NOW", "EARLY BUY"}:
                    failures = self._trigger_failures(result)
                    self._add_rejection(ticker, "Trigger Engine", failures, dict(result.get("trigger_metrics", {}) or {}))

    def build_summary(self) -> Dict[str, Any]:
        if not self.enabled:
            return {}

        with self._lock:
            top_rules = [
                {"rule": rule, "rejected": count}
                for rule, count in self.rule_rejection_counts.most_common(self.top_rules)
            ]
            return {
                "universe": self.universe_size,
                "stages": {
                    stage: dict(counts)
                    for stage, counts in self.stage_counts.items()
                },
                "trigger_modules": {
                    name: dict(counts)
                    for name, counts in self.trigger_module_counts.items()
                },
                "decisions": dict(self.decision_counts),
                "most_restrictive_rules": top_rules,
                "rejections": [rejection.to_dict() for rejection in self.rejections],
            }

    def format_summary(self) -> str:
        summary = self.build_summary()
        if not summary:
            return ""

        universe_size = summary.get("universe", 0)
        stages = summary["stages"]
        decisions = summary["decisions"]
        modules = summary["trigger_modules"]
        top_rules = summary["most_restrictive_rules"]

        def get_counts(stage_name):
            return stages.get(stage_name, {"passed": 0, "rejected": 0})

        quality_counts = get_counts("quality")
        setup_counts = get_counts("setup")
        transition_counts = get_counts("transition")
        trigger_counts = get_counts("trigger")

        lines = [
            f"--- SCANNER FUNNEL DIAGNOSTICS ---",
            f"Universe Size: {universe_size}",
            "",
            f"1. Quality Filter:      {quality_counts['passed']:>5} Passed | {quality_counts['rejected']:>5} Rejected",
            f"2. Setup Engine:        {setup_counts['passed']:>5} Passed | {setup_counts['rejected']:>5} Rejected (Informational)",
            f"3. Transition Engine:   {transition_counts['passed']:>5} Passed | {transition_counts['rejected']:>5} Rejected (Informational)",
            f"4. Trigger Engine:      {trigger_counts['passed']:>5} Passed | {trigger_counts['rejected']:>5} Rejected",
            "",
            "--- TRIGGER DECISIONS ---",
            f"BUY NOW:   {decisions.get('BUY NOW', 0)}",
            f"EARLY BUY: {decisions.get('EARLY BUY', 0)}",
            f"WATCH:     {decisions.get('WATCH', 0)}",
            f"WAIT:      {decisions.get('WAIT', 0)}",
        ]

        if top_rules:
            lines.extend(["", "--- MOST RESTRICTIVE RULES ---"])
            for idx, item in enumerate(top_rules, start=1):
                lines.append(f"{idx}. {item['rule']:<30} | Rejected {item['rejected']} stocks")

        lines.append("\n--- END OF REPORT ---")
        return "\n".join(lines)
