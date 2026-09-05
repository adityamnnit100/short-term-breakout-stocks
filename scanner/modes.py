"""Independent scanner modes for watchlist and entry selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
from .config import ScannerConfig
from .indicators import atr, ema
from .formatting import build_reason_label, build_reason_text, confidence, recommendation, setup_id, trade_quality
from quality_filter import QualityContext, QualityFilterEngine, QualityResult
from setup_engine import SetupEngine
from transition_engine import TransitionEngine
from trigger_engine import TriggerEngine


@dataclass
class FilterResult:
    name: str
    passed: Optional[bool]
    score: float
    detail: Optional[Dict[str, object]] = None


class BaseScanner:
    """Shared base class for all scanner modes."""

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        quality_engine: Optional[QualityFilterEngine] = None,
        setup_engine: Optional[SetupEngine] = None,
        transition_engine: Optional[TransitionEngine] = None,
        trigger_engine: Optional[TriggerEngine] = None,
        scan_mode: str = "Watchlist",
    ):
        self.config = config or ScannerConfig()
        self.quality_engine = quality_engine or QualityFilterEngine(self.config)
        self.setup_engine = setup_engine or SetupEngine(self.config)
        self.transition_engine = transition_engine or TransitionEngine(self.config)
        self.trigger_engine = trigger_engine or TriggerEngine(self.config)
        self.scan_mode = scan_mode

    def prepare_shared_evaluation(
        self, df: pd.DataFrame, ticker: str, sector: str = "Unknown"
    ) -> Dict[str, object]:
        """Prepares the DataFrame and QualityContext to be shared between scanner modes."""
        prepared = self._prepare_df(df)
        if prepared.empty or len(prepared) < self.config.min_candles:
            return {"prepared": prepared, "context": None}
        context = self._build_quality_context(prepared, ticker, sector)
        return {"prepared": prepared, "context": context}

    def _evaluate(
        self,
        df: pd.DataFrame,
        ticker: str,
        sector: str,
        prepared: Optional[pd.DataFrame],
        context: Optional[QualityContext],
    ) -> Dict[str, object]:
        """Runs the full evaluation pipeline and returns intermediate results."""
        prepared = prepared if prepared is not None else self._prepare_df(df)
        if prepared.empty or len(prepared) < self.config.min_candles:
            return {"ticker": ticker, "passed": False, "score": 0.0, "reasons": [], "reason_label": "Insufficient data"}

        context = context if context is not None else self._build_quality_context(prepared, ticker, sector)
        if context is None:
            return {"ticker": ticker, "passed": False, "score": 0.0, "reasons": [], "reason_label": "Insufficient data"}

        quality = self._check_quality(context)
        if not quality.passed:
            return {
                "ticker": ticker,
                "passed": False,
                "score": 0.0,
                "reasons": quality.failed_checks,
                "reason_label": quality.rejection_reason or "Quality filter failed",
                **self._quality_payload(quality),
            }

        market_tape_ok, market_tape_reason = self._market_tape_check(context)
        if not market_tape_ok:
            return {
                "ticker": ticker,
                "passed": False,
                "score": 0.0,
                "reasons": [market_tape_reason],
                "reason_label": market_tape_reason,
                "quality_passed": True,
                "quality_failed_checks": [],
                "quality_passed_checks": ["market_tape_checked"],
                "quality_details": {"market_tape": {"passed": False, "reason": market_tape_reason}},
                "quality_gate_results": {"market_tape": {"passed": False, "reason": market_tape_reason}},
            }

        setup_result = self._check_setup(context)
        transition_result = self._check_transition(context, setup_result)
        trigger_result = self._check_trigger(context, setup_result, transition_result)

        common_results = self._get_common_results(context, quality, setup_result, transition_result, trigger_result)

        return {"context": context, "quality": quality, "setup_result": setup_result, "transition_result": transition_result, "trigger_result": trigger_result, "common_results": common_results}

    def evaluate(
        self,
        df: pd.DataFrame,
        ticker: str,
        sector: str = "Unknown",
        prepared: Optional[pd.DataFrame] = None,
        context: Optional[QualityContext] = None,
    ) -> Dict[str, object]:
        return self._evaluate(df, ticker, sector, prepared, context)

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        prepared = df.copy()
        for column in ["Open", "High", "Low", "Close", "Volume"]:
            if column in prepared.columns:
                prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
        return prepared.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    def _market_tape_check(self, context: QualityContext) -> tuple[bool, str]:
        regime = str(context.market_regime or "UNKNOWN").upper()
        sector_strength = float(getattr(context, "sector_strength", 0.0) or 0.0)
        market_regime_score = float(getattr(context, "market_regime_score", 0.0) or 0.0)

        if regime in {"BEARISH", "STRONG BEAR"}:
            return False, "Weak market tape"
        if regime == "CAUTION" and (sector_strength < 5.0 or market_regime_score < 0.0):
            return False, "Weak market tape"
        if regime == "NEUTRAL" and sector_strength < 4.0 and market_regime_score < 0.2:
            return False, "Weak market tape"
        return True, ""

    def _ema(self, series: pd.Series, length: int) -> pd.Series:
        return ema(series, length)

    def _atr(self, df: pd.DataFrame) -> pd.Series:
        return atr(df, self.config.atr_window)

    def _build_quality_context(self, df: pd.DataFrame, ticker: str, sector: str = "Unknown") -> Optional[QualityContext]:
        return self.quality_engine.build_context(df, ticker=ticker, sector=sector)

    def _check_quality(self, context: QualityContext) -> QualityResult:
        return self.quality_engine.evaluate(context)

    def _check_setup(self, context: QualityContext):
        return self.setup_engine.evaluate(context)

    def _check_transition(self, context: QualityContext, setup_result):
        transition_context = self.transition_engine.build_context(context, setup_result, scan_mode=self.scan_mode)
        return self.transition_engine.evaluate(transition_context)

    def _check_trigger(self, context: QualityContext, setup_result, transition_result):
        trigger_context = self.trigger_engine.build_context(context, setup_result, transition_result, scan_mode=self.scan_mode)
        return self.trigger_engine.evaluate(trigger_context)

    @staticmethod
    def _quality_payload(quality: QualityResult) -> Dict[str, object]:
        return {
            "quality_passed": quality.passed,
            "quality_failed_checks": list(quality.failed_checks),
            "quality_passed_checks": list(quality.passed_checks),
            "quality_details": dict(quality.details),
            "quality_gate_results": dict(getattr(quality, "gate_results", {}) or {}),
        }

    @staticmethod
    def _gate_payload(result, score_attr: str = "score") -> Dict[str, object]:
        return {
            "passed": bool(getattr(result, "passed", False)),
            "score": float(getattr(result, score_attr, 0.0) or 0.0),
            "reasons": list(getattr(result, "reasons", [])),
            "weaknesses": list(getattr(result, "weaknesses", [])),
            "metrics": dict(getattr(result, "metrics", {}) or {}),
        }

    def _bb_width(self, df: pd.DataFrame) -> pd.Series:
        close = pd.to_numeric(df["Close"], errors="coerce")
        rolling_mean = close.rolling(20).mean()
        rolling_std = close.rolling(20).std()
        return (rolling_std * 2.0) / rolling_mean.replace(0, pd.NA) * 100.0

    def _reason_label(self, reasons: List[str]) -> str:
        return build_reason_label(reasons)

    def _build_reason_text(self, reasons: List[str], score: float) -> str:
        return build_reason_text(reasons, score)

    def _trade_quality(self, score: float) -> str:
        return trade_quality(score)

    def _setup_id(self, score: float, reasons: List[str]) -> str:
        return setup_id(score, reasons)

    def _recommendation(self, score: float, reasons: List[str]) -> str:
        return recommendation(score, reasons)

    def _confidence(self, score: float) -> str:
        return confidence(score)

    def _get_common_results(self, context, quality_result, setup_result, transition_result, trigger_result):
        """Builds the common dictionary of results from all engine stages."""
        setup_prefix = {
            "setup_score": setup_result.setup_score,
            "setup_category": setup_result.category,
            "setup_reasons": setup_result.reasons,
            "setup_weaknesses": setup_result.weaknesses,
            "setup_base_score": setup_result.base_score,
            "setup_compression_score": setup_result.compression_score,
            "setup_volume_score": setup_result.volume_score,
            "setup_resistance_score": setup_result.resistance_score,
            "setup_structure_score": setup_result.structure_score,
            "setup_risk_score": setup_result.risk_score,
            "setup_qualifies": setup_result.qualifies,
            "setup_gate_results": dict(getattr(setup_result, "gate_results", {}) or {}),
        }
        transition_prefix = {
            "transition_score": transition_result.transition_score,
            "transition_category": transition_result.category,
            "transition_setup_velocity_score": transition_result.setup_velocity_score,
            "transition_rs_acceleration_score": transition_result.rs_acceleration_score,
            "transition_volume_transition_score": transition_result.volume_transition_score,
            "transition_compression_evolution_score": transition_result.compression_evolution_score,
            "transition_resistance_pressure_score": transition_result.resistance_pressure_score,
            "transition_price_acceptance_score": transition_result.price_acceptance_score,
            "transition_opportunity_velocity_score": transition_result.opportunity_velocity_score,
            "transition_reasons": transition_result.reasons,
            "transition_weaknesses": transition_result.weaknesses,
            "transition_qualifies": transition_result.qualifies,
            "transition_metrics": transition_result.metrics,
            "transition_gate_results": dict(getattr(transition_result, "gate_results", {}) or {}),
        }
        trigger_prefix = {
            "trigger_decision": trigger_result.decision,
            "trigger_confidence": trigger_result.confidence,
            "trigger_score": trigger_result.trigger_score,
            "trigger_priority_score": trigger_result.priority_score,
            "trigger_rank_percentile": trigger_result.rank_percentile,
            "trigger_qualifies": trigger_result.qualifies,
            "trigger_hard_gate_failures": trigger_result.hard_gate_failures,
            "trigger_reasons": trigger_result.reasons,
            "trigger_weaknesses": trigger_result.weaknesses,
            "trigger_passed_modules": trigger_result.passed_modules,
            "trigger_failed_modules": trigger_result.failed_modules,
            "trigger_module_results": trigger_result.module_results,
            "trigger_metrics": trigger_result.metrics,
            "quality_market_regime": context.market_regime,
            "quality_market_regime_score": context.market_regime_score,
            **self._quality_payload(quality_result),
        }
        return {**setup_prefix, **transition_prefix, **trigger_prefix}


class WatchlistScanner(BaseScanner):
    """Early-detection scanner for stocks building a base."""

    def evaluate(
        self,
        df: pd.DataFrame,
        ticker: str,
        sector: str = "Unknown",
        prepared: Optional[pd.DataFrame] = None,
        context: Optional[QualityContext] = None,
    ) -> Dict[str, object]:
        eval_results = self._evaluate(df, ticker, sector, prepared, context)
        if "common_results" not in eval_results:
            return eval_results

        context = eval_results["context"]
        setup_result = eval_results["setup_result"]
        transition_result = eval_results["transition_result"]

        # New scoring model: Watchlist score is a blend of Setup and Transition quality.
        score = (
            setup_result.setup_score * self.config.watchlist_setup_weight
            + transition_result.transition_score * self.config.watchlist_transition_weight
        )
        passed = score >= self.config.watchlist_min_score
        reasons = setup_result.reasons + transition_result.reasons

        return {
            "ticker": ticker,
            "passed": passed,
            "score": round(score, 2),
            "reasons": reasons,
            "reason_label": self._reason_label(reasons),
            "sector": sector,
            "trend": "Bullish" if context.latest_close > context.latest_ema20 else "Neutral",
            "base_score": setup_result.base_score,
            "volume_score": setup_result.volume_score,
            "relative_strength": transition_result.rs_acceleration_score,
            "atr_contraction": setup_result.metrics.get("compression", {}).get("atr_contraction_pct", 0.0),
            "days_in_consolidation": int(context.days_in_consolidation),
            "reason_text": self._build_reason_text(reasons, round(score, 2)),
            "trade_quality": self._trade_quality(round(score, 2)),
            "setup_id": self._setup_id(round(score, 2), reasons),
            "recommendation": self._recommendation(round(score, 2), reasons),
            "confidence": self._confidence(round(score, 2)),
            **eval_results["common_results"],
        }


class EntryScanner(BaseScanner):
    """Actionable entry scanner for confirmed breakouts and retests."""

    def evaluate(
        self,
        df: pd.DataFrame,
        ticker: str,
        sector: str = "Unknown",
        prepared: Optional[pd.DataFrame] = None,
        context: Optional[QualityContext] = None,
    ) -> Dict[str, object]:
        eval_results = self._evaluate(df, ticker, sector, prepared, context)
        if "common_results" not in eval_results:
            return eval_results

        context = eval_results["context"]
        setup_result = eval_results["setup_result"]
        transition_result = eval_results["transition_result"]
        trigger_result = eval_results["trigger_result"]
        prepared_df = eval_results.get("prepared")
        if prepared_df is None:
            prepared_df = self._prepare_df(df)

        latest_close = context.latest_close
        latest_atr = context.latest_atr
        avg_volume = context.avg_volume
        current_volume = context.current_volume
        breakout_volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0

        # New scoring model: Entry score is a blend of Setup, Transition, and Trigger quality.
        # The priority_score from the trigger engine is used for final ranking.
        score = (
            setup_result.setup_score * self.config.entry_setup_weight
            + transition_result.transition_score * self.config.entry_transition_weight
            + trigger_result.trigger_score * self.config.entry_trigger_weight
        )

        # The 'passed' flag for an entry signal is now determined by the Trigger Engine's final decision.
        # This makes the scanner actionable, only showing stocks classified as ready for entry.
        passed = trigger_result.decision in {"BUY NOW", "EARLY BUY"}

        # Combine reasons from all qualifying engines for a comprehensive view.
        reasons: List[str] = setup_result.reasons + transition_result.reasons + trigger_result.reasons

        return {
            "ticker": ticker,
            "passed": passed,
            "score": round(score, 2),
            "reasons": reasons,
            "reason_label": self._reason_label(reasons),
            "sector": sector,
            "entry_price": round(latest_close, 2),
            "stop_loss": round(latest_close - latest_atr * 1.5, 2),
            "risk_pct": round((latest_atr / latest_close) * 100.0, 2) if latest_close > 0 else 0.0,
            "target_1": round(latest_close + latest_atr * 2.0, 2),
            "target_2": round(latest_close + latest_atr * 3.0, 2),
            "risk_reward": round(2.0, 2),
            "breakout_date": prepared_df.index[-1] if prepared_df is not None and not prepared_df.empty else None,
            "breakout_volume_ratio": round(breakout_volume_ratio, 2),
            "reason_text": self._build_reason_text(reasons, round(score, 2)),
            "trade_quality": self._trade_quality(round(score, 2)),
            "setup_id": self._setup_id(round(score, 2), reasons),
            "recommendation": self._recommendation(round(score, 2), reasons),
            "confidence": self._confidence(round(score, 2)),
            **eval_results["common_results"],
        }


class ShortTermScanner(EntryScanner):
    """Short-term actionable scanner that applies intraday VWAP/RVol/close-location gates."""

    def evaluate(
        self,
        df: pd.DataFrame,
        ticker: str,
        sector: str = "Unknown",
        prepared: Optional[pd.DataFrame] = None,
        context: Optional[QualityContext] = None,
    ) -> Dict[str, object]:
        base = super().evaluate(df, ticker, sector, prepared, context)
        # If the base evaluation did not produce common results, return as-is
        if "common_results" not in base:
            return base

        prepared_df = base.get("breakout_date")
        # retrieve prepared frame (we may recompute to access VWAP/RVol)
        prepared_frame = prepared if prepared is not None else self._prepare_df(df)
        if prepared_frame is None or prepared_frame.empty:
            return base

        last = prepared_frame.iloc[-1]
        latest_close = float(last.get("Close", 0.0))

        reasons = list(base.get("reasons", []) or [])

        # VWAP hold check
        vwap_val = None
        try:
            vwap_val = float(last.get("VWAP")) if "VWAP" in prepared_frame.columns else None
        except Exception:
            vwap_val = None

        if vwap_val is not None and vwap_val > 0:
            hold_min = float(getattr(self.config, "trigger_intraday_high_hold_min", 0.9) or 0.9)
            if not (latest_close >= vwap_val * hold_min):
                reasons.append("VWAP hold failed")

        # Relative volume check
        rvol_ok = True
        try:
            if f"RVol_{getattr(self.config, 'rvol_window', 20)}" in prepared_frame.columns:
                rvol_val = float(last.get(f"RVol_{getattr(self.config, 'rvol_window', 20)}"))
            elif "RVol_20" in prepared_frame.columns:
                rvol_val = float(last.get("RVol_20"))
            else:
                # compute simple RVol on the fly
                from .indicators import relative_volume

                rser = relative_volume(prepared_frame, window=int(getattr(self.config, "rvol_window", 20)))
                rvol_val = float(rser.iloc[-1]) if not rser.empty else 0.0
        except Exception:
            rvol_val = 0.0

        try:
            rvol_min = float(getattr(self.config, "trigger_intraday_rvol_min", 1.4) or 1.4)
            if rvol_val < rvol_min:
                rvol_ok = False
                reasons.append("RVol below threshold")
        except Exception:
            pass

        # Close location check (within upper band of range)
        try:
            high = float(last.get("High", 0.0))
            low = float(last.get("Low", 0.0))
            loc = 0.0
            if high > low:
                loc = (latest_close - low) / (high - low)
            close_loc_min = float(getattr(self.config, "trigger_pocket_pivot_close_location_min", 0.7) or 0.7)
            if loc < close_loc_min:
                reasons.append("Close not high enough in bar")
        except Exception:
            pass

        # If any intraday gate failed, mark as not passed and update reason_label
        if any(r in reasons for r in ["VWAP hold failed", "RVol below threshold", "Close not high enough in bar"]):
            base["passed"] = False
            base["reasons"] = reasons
            base["reason_label"] = self._reason_label(reasons)

        return base
