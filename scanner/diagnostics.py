"""Diagnostics helpers for scanner pipeline instrumentation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Mapping, Optional


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


class DiagnosticsCollector:
    """Thread-safe collector for scan-stage pass/fail instrumentation."""

    def __init__(self, enabled: bool = False, top_rules: int = 3):
        self.enabled = enabled
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

    @staticmethod
    def _quality_failures(result: Mapping[str, Any]) -> List[DiagnosticsRuleHit]:
        details = result.get("quality_gate_results", {}) or {}
        failed = []
        for check in result.get("quality_failed_checks", []) or []:
            detail = {}
            if str(check) == "Liquidity Too Low":
                detail = details.get("liquidity", {}).get("detail", {})
                actual = detail.get("avg_volume")
                required = detail.get("min_avg_volume")
            elif str(check) == "Average Daily Turnover Too Low":
                detail = details.get("liquidity", {}).get("detail", {})
                actual = detail.get("avg_turnover")
                required = detail.get("min_avg_turnover")
            elif str(check) in {"Trend Template Failed", "EMA Alignment Failed", "Higher Highs Failed", "Higher Lows Failed"}:
                detail = details.get("trend", {}).get("detail", {})
                actual = detail.get("trend_template_pass")
                if str(check) == "EMA Alignment Failed":
                    actual = detail.get("ema_alignment")
                elif str(check) == "Higher Highs Failed":
                    actual = detail.get("higher_highs")
                elif str(check) == "Higher Lows Failed":
                    actual = detail.get("higher_lows")
                required = True
            elif str(check) == "Relative Strength Below Threshold":
                detail = details.get("relative_strength", {}).get("detail", {})
                actual = detail.get("relative_strength")
                required = detail.get("min_relative_strength")
            elif str(check) == "Weak Sector":
                detail = details.get("sector", {}).get("detail", {})
                actual = detail.get("sector_strength")
                required = detail.get("min_sector_strength")
            elif str(check) == "Market Cap Below Minimum":
                detail = details.get("market_cap", {}).get("detail", {})
                actual = detail.get("market_cap_cr")
                required = detail.get("min_market_cap_cr")
            elif str(check) == "Market Cap Above Maximum":
                detail = details.get("market_cap", {}).get("detail", {})
                actual = detail.get("market_cap_cr")
                required = detail.get("max_market_cap_cr")
            else:
                detail = dict(details.get("market_cap", {}).get("detail", {}) or {})
                actual = None
                required = None
            failed.append(DiagnosticsRuleHit(rule=str(check), actual=actual, required=required, metrics=dict(detail)))
        return failed

    @staticmethod
    def _stage_rule_hits(stage: str, gate_results: Mapping[str, Any]) -> List[DiagnosticsRuleHit]:
        hits: List[DiagnosticsRuleHit] = []
        threshold_map = {
            "setup": {
                "base_quality": 60.0,
                "compression": 40.0,
                "volume_dryup": 35.0,
                "resistance": 35.0,
                "structure": 40.0,
                "risk": 35.0,
            },
            "transition": {
                "setup_velocity": 55.0,
                "rs_acceleration": 55.0,
                "volume_transition": 55.0,
                "compression_evolution": 55.0,
                "resistance_pressure": 50.0,
                "price_acceptance": 50.0,
                "opportunity_velocity": 60.0,
            },
        }
        for name, payload in gate_results.items():
            if payload.get("passed", False):
                continue
            metrics = dict(payload.get("metrics", {}) or {})
            actual = payload.get("score", 0.0)
            required = threshold_map.get(stage, {}).get(name)
            if stage == "setup":
                required = required if required is not None else 0.0
            elif stage == "transition":
                required = required if required is not None else 0.0
            hits.append(DiagnosticsRuleHit(rule=name, actual=actual, required=required, metrics=metrics))
        return hits

    @staticmethod
    def _trigger_failures(result: Mapping[str, Any]) -> List[DiagnosticsRuleHit]:
        module_results = result.get("trigger_module_results", {}) or {}
        hits: List[DiagnosticsRuleHit] = []
        for name, payload in module_results.items():
            if payload.get("passed", False):
                continue
            metrics = dict(payload.get("metrics", {}) or {})
            actual = payload.get("score", 0.0)
            required = None
            if name == "breakout_confirmation":
                required = 1.8
            elif name == "relative_volume":
                required = 1.2
            elif name == "closing_strength":
                required = 0.75
            elif name == "rs_confirmation":
                required = 105.0
            elif name == "volume_confirmation":
                required = 60.0
            elif name == "pocket_pivot":
                required = 1.5
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

            if "setup_qualifies" in result or "setup_gate_results" in result:
                setup_passed = bool(result.get("setup_qualifies", False))
                self._record_stage("setup", setup_passed)
                if not setup_passed:
                    failures = self._stage_rule_hits("setup", result.get("setup_gate_results", {}) or {})
                    self._add_rejection(ticker, "Setup Engine", failures, dict(result.get("setup_metrics", {}) or {}))

            if "transition_qualifies" in result or "transition_gate_results" in result:
                transition_passed = bool(result.get("transition_qualifies", False))
                self._record_stage("transition", transition_passed)
                if not transition_passed:
                    failures = self._stage_rule_hits("transition", result.get("transition_gate_results", {}) or {})
                    self._add_rejection(ticker, "Transition Engine", failures, dict(result.get("transition_metrics", {}) or {}))

            if "trigger_decision" in result or "trigger_module_results" in result:
                decision = str(result.get("trigger_decision", "WAIT") or "WAIT")
                self.decision_counts[decision] += 1
                trigger_passed = decision in {"BUY NOW", "EARLY BUY"}
                self._record_stage("trigger", trigger_passed)

                module_results = result.get("trigger_module_results", {}) or {}
                for name, payload in module_results.items():
                    bucket = self.trigger_module_counts.setdefault(name, {"passed": 0, "failed": 0})
                    if payload.get("passed", False):
                        bucket["passed"] += 1
                    else:
                        bucket["failed"] += 1

                if not trigger_passed:
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

        stages = summary["stages"]
        decisions = summary["decisions"]
        modules = summary["trigger_modules"]
        top_rules = summary["most_restrictive_rules"]

        lines = [
            f"Universe {summary['universe']}",
            "",
            f"Quality Filter  Passed: {stages['quality']['passed']}  Rejected: {stages['quality']['rejected']}",
            "",
            f"Setup Engine    Passed: {stages['setup']['passed']}  Rejected: {stages['setup']['rejected']}",
            "",
            f"Transition Engine  Passed: {stages['transition']['passed']}  Rejected: {stages['transition']['rejected']}",
            "",
            "Trigger Engine",
        ]
        for name in sorted(modules.keys()):
            counts = modules[name]
            label = name.replace("_", " ").title()
            lines.append(f"{label}  Passed: {counts['passed']}  Failed: {counts['failed']}")
        lines.extend(
            [
                "",
                f"BUY NOW {decisions.get('BUY NOW', 0)}",
                f"EARLY BUY {decisions.get('EARLY BUY', 0)}",
                f"WATCH {decisions.get('WATCH', 0)}",
                f"WAIT {decisions.get('WAIT', 0)}",
            ]
        )
        if top_rules:
            lines.extend(["", "Most Restrictive Rules"])
            for idx, item in enumerate(top_rules, start=1):
                lines.append(f"{idx}. {item['rule']} - Rejected {item['rejected']} stocks")
        return "\n".join(lines)
