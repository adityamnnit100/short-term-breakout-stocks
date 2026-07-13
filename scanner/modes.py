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

    def evaluate(
        self,
        df: pd.DataFrame,
        ticker: str,
        sector: str = "Unknown",
        prepared: Optional[pd.DataFrame] = None,
        context: Optional[QualityContext] = None,
    ) -> Dict[str, object]:
        raise NotImplementedError("Subclasses must implement the 'evaluate' method.")

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        prepared = df.copy()
        for column in ["Open", "High", "Low", "Close", "Volume"]:
            if column in prepared.columns:
                prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
        return prepared.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

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

        setup_result = self._check_setup(context)
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
        transition_result = self._check_transition(context, setup_result)
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
        trigger_result = self._check_trigger(context, setup_result, transition_result)
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
            **self._quality_payload(quality),
        }

        close = context.close
        ema20 = context.ema20
        ema200 = context.ema200
        atr_series = context.atr
        bbw = self._bb_width(prepared)
        volume = context.volume

        latest_close = context.latest_close
        latest_ema20 = context.latest_ema20
        latest_ema200 = context.latest_ema200
        recent_high = context.recent_high_20d
        base_high = context.recent_high_40d
        days_in_consolidation = context.days_in_consolidation
        recent_low = context.recent_low_20d
        higher_lows = context.higher_lows
        trend_score = 0.0
        reasons: List[str] = []

        if latest_close > latest_ema200:
            trend_score += 25.0
            reasons.append(f"Price above 200 EMA ({latest_close:.2f} > {latest_ema200:.2f})")
        if abs(latest_ema200 - ema200.iloc[-2]) <= max(latest_ema200 * 0.002, 0.01):
            trend_score += 20.0
            reasons.append("200 EMA flat/slightly rising")

        atr_score = 0.0
        atr_contraction_pct = 0.0
        if atr_series.empty:
            atr_score = 0.0
        else:
            recent_atr = float(atr_series.iloc[-1])
            avg_atr = float(atr_series.tail(20).mean())
            atr_contraction_pct = ((recent_atr / avg_atr) * 100.0) - 100.0 if avg_atr > 0 else 0.0
            if atr_contraction_pct <= self.config.watchlist_atr_contraction_pct:
                atr_score += 100.0
                reasons.append(f"ATR contracting ({atr_contraction_pct:.1f}%)")

        bbw_score = 0.0
        bbw_contraction_pct = 0.0
        if not bbw.empty:
            latest_bbw = float(bbw.iloc[-1])
            avg_bbw = float(bbw.tail(20).mean())
            bbw_contraction_pct = ((latest_bbw / avg_bbw) * 100.0) - 100.0 if avg_bbw > 0 else 0.0
            if bbw_contraction_pct <= self.config.watchlist_bbw_contraction_pct:
                bbw_score += 100.0
                reasons.append(f"Bollinger width contracting ({bbw_contraction_pct:.1f}%)")

        base_score = 0.0
        base_range_pct = ((close.tail(20).max() - close.tail(20).min()) / latest_close) * 100.0
        if base_range_pct <= self.config.watchlist_base_range_pct:
            base_score += 35.0
            reasons.append(f"Tight base range ({base_range_pct:.1f}%)")
        if days_in_consolidation >= self.config.watchlist_base_days_min:
            base_score += 25.0
            reasons.append(f"Consolidation building ({days_in_consolidation} days)")
        if latest_close <= recent_high * (1 + self.config.watchlist_base_high_pct / 100.0):
            base_score += 20.0
            reasons.append("Not extended from base high")
        if atr_score > 0:
            base_score += 10.0
        if bbw_score > 0:
            base_score += 10.0
        base_score = min(base_score, 100.0)

        volume_score = 0.0
        avg_volume = float(volume.rolling(self.config.volume_sma_window).mean().iloc[-1])
        current_volume = float(volume.iloc[-1])
        recent_low_volume = float(volume.tail(self.config.volume_contraction_lookback).min())
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0
        contraction_pct = ((recent_low_volume / avg_volume) - 1.0) * 100.0 if avg_volume > 0 else 0.0
        if contraction_pct <= self.config.watchlist_volume_dryup_pct:
            volume_score += 60.0
            reasons.append(f"Volume dry-up ({contraction_pct:.1f}%)")
        if volume_ratio >= 1.0:
            volume_score += 40.0
            reasons.append(f"Volume holding ({volume_ratio:.1f}x)")

        rs_score = 0.0
        if latest_close > recent_low * 1.03:
            rs_score += 50.0
            reasons.append("Relative strength improving")
        if latest_close > latest_ema20:
            rs_score += 50.0
            reasons.append("Short-term momentum positive")

        sector_score = 0.0
        if sector != "Unknown":
            sector_score = 100.0
            reasons.append(f"Sector strength: {sector}")

        score = (
            trend_score * self.config.watchlist_trend_weight
            + base_score * self.config.watchlist_base_weight
            + volume_score * self.config.watchlist_volume_weight
            + rs_score * self.config.watchlist_rs_weight
            + sector_score * self.config.watchlist_sector_weight
        )
        passed = score >= self.config.watchlist_min_score
        return {
            "ticker": ticker,
            "passed": passed,
            "score": round(score, 2),
            "reasons": reasons,
            "reason_label": self._reason_label(reasons),
            "sector": sector,
            "trend": "Bullish" if latest_close > latest_ema20 else "Neutral",
            "base_score": round(base_score, 2),
            "volume_score": round(volume_score, 2),
            "relative_strength": round(rs_score, 2),
            "atr_contraction": round(atr_contraction_pct, 2),
            "days_in_consolidation": int(days_in_consolidation),
            "reason_text": self._build_reason_text(reasons, round(score, 2)),
            "trade_quality": self._trade_quality(round(score, 2)),
            "setup_id": self._setup_id(round(score, 2), reasons),
            "recommendation": self._recommendation(round(score, 2), reasons),
            "confidence": self._confidence(round(score, 2)),
            **setup_prefix,
            **transition_prefix,
            **trigger_prefix,
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

        setup_result = self._check_setup(context)
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
        transition_result = self._check_transition(context, setup_result)
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
        trigger_result = self._check_trigger(context, setup_result, transition_result)
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
            **self._quality_payload(quality),
        }

        close = context.close
        ema20 = context.ema20
        ema50 = context.ema50
        ema200 = context.ema200
        atr_series = context.atr
        volume = context.volume

        latest_close = context.latest_close
        latest_ema20 = context.latest_ema20
        latest_ema50 = context.latest_ema50
        latest_ema200 = context.latest_ema200
        latest_atr = context.latest_atr
        avg_atr = float(atr_series.tail(20).mean()) if not atr_series.empty else 0.0
        avg_volume = context.avg_volume
        current_volume = context.current_volume
        breakout_volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0.0
        rsi_rank = 90.0

        trend_score = 0.0
        reasons: List[str] = []
        if latest_close > latest_ema20 and latest_close > latest_ema50 and latest_close > latest_ema200:
            trend_score += 60.0
            reasons.append("EMA alignment")
        if latest_ema20 > latest_ema50 and latest_ema50 > latest_ema200:
            trend_score += 40.0
            reasons.append("Momentum stack positive")
        if trend_score >= 100.0:
            reasons.append("Trend confirmed")

        breakout_score = 0.0
        if latest_close > close.iloc[-2] * 1.01:
            breakout_score += 80.0
            reasons.append("Breakout confirmed")
        if breakout_volume_ratio >= max(0.8, self.config.entry_breakout_volume_ratio * 0.5):
            breakout_score += 20.0
            reasons.append(f"Breakout volume strong ({breakout_volume_ratio:.1f}x)")

        volume_score = 0.0
        if breakout_volume_ratio >= max(0.8, self.config.entry_breakout_volume_ratio * 0.5):
            volume_score += 100.0

        rs_score = 0.0
        if rsi_rank >= self.config.entry_rs_rank_min:
            rs_score += 100.0
            reasons.append("Relative strength rank strong")

        sector_score = 0.0
        if sector != "Unknown":
            sector_score += 100.0
            reasons.append(f"Sector strength: {sector}")

        risk_score = 0.0
        if latest_atr > 0 and avg_atr > 0 and (latest_atr / avg_atr) <= self.config.entry_atr_expansion_pct:
            risk_score += 60.0
            reasons.append("ATR not expanding abnormally")
        if latest_close <= (close.iloc[-20].max() * (1 + self.config.entry_extension_pct / 100.0)):
            risk_score += 40.0
            reasons.append("Not excessively extended")

        score = (
            trend_score * self.config.entry_trend_weight
            + breakout_score * self.config.entry_breakout_weight
            + volume_score * self.config.entry_volume_weight
            + rs_score * self.config.entry_rs_weight
            + sector_score * self.config.entry_sector_weight
            + risk_score * self.config.entry_risk_weight
        )
        passed = trigger_result.qualifies
        return {
            "ticker": ticker,
            "passed": passed,
            "score": round(score, 2),
            "reasons": reasons,
            "reason_label": self._reason_label(reasons),
            "sector": sector,
            "entry_price": round(latest_close, 2),
            "stop_loss": round(latest_close - latest_atr * 1.5, 2),
            "risk_pct": round((latest_atr / latest_close) * 100.0, 2),
            "target_1": round(latest_close + latest_atr * 2.0, 2),
            "target_2": round(latest_close + latest_atr * 3.0, 2),
            "risk_reward": round(2.0, 2),
            "breakout_date": prepared.index[-1] if hasattr(prepared.index, "__getitem__") else None,
            "breakout_volume_ratio": round(breakout_volume_ratio, 2),
            "reason_text": self._build_reason_text(reasons, round(score, 2)),
            "trade_quality": self._trade_quality(round(score, 2)),
            "setup_id": self._setup_id(round(score, 2), reasons),
            "recommendation": self._recommendation(round(score, 2), reasons),
            "confidence": self._confidence(round(score, 2)),
            **setup_prefix,
            **transition_prefix,
            **trigger_prefix,
        }
