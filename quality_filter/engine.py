"""Quality filter engine using a chain of responsibility."""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

import pandas as pd

from scanner.config import ScannerConfig
from scanner.indicators import atr, ema
from scanner.sector import calculate_sector_score

from .liquidity_gate import LiquidityGate
from .market_gate import MarketGate
from .marketcap_gate import MarketCapGate, get_market_cap_cr_quietly
from .models import GateResult, QualityContext, QualityGate, QualityResult
from .rs_gate import RSGate
from .sector_gate import SectorGate
from .trend_gate import TrendGate

logger = logging.getLogger("AlphaScanner.QualityFilter")


class QualityFilterEngine:
    """Strict quality gate that validates candidate eligibility."""

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
        gates: Optional[Iterable[QualityGate]] = None,
        benchmark: Optional[pd.Series] = None,
        market_regime_snapshot: Optional[dict] = None,
    ):
        self.config = config or ScannerConfig()
        self._context_cache: dict = {}
        self.gates: List[QualityGate] = list(gates) if gates is not None else [
            MarketGate(),
            LiquidityGate(),
            MarketCapGate(),
            TrendGate(),
            RSGate(),
            SectorGate(),
        ]
        self.benchmark = benchmark if benchmark is not None else pd.Series(dtype=float)
        self.market_regime_snapshot = market_regime_snapshot if market_regime_snapshot is not None else {"regime": "UNKNOWN", "score": 0.0}

    def build_context(self, df: pd.DataFrame, ticker: str, sector: str = "Unknown") -> Optional[QualityContext]:
        if df is None or df.empty:
            return None

        cache_key = (ticker, id(df), len(df))
        cached = self._context_cache.get(cache_key)
        if cached is not None:
            return cached

        frame = df.copy()
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        high = pd.to_numeric(frame["High"], errors="coerce")
        low = pd.to_numeric(frame["Low"], errors="coerce")
        open_ = pd.to_numeric(frame["Open"], errors="coerce")
        volume = pd.to_numeric(frame["Volume"], errors="coerce")
        if close.empty or high.empty or low.empty or volume.empty:
            return None

        ema20 = ema(close, self.config.ema_fast)
        ema50 = ema(close, self.config.ema_medium)
        ema200 = ema(close, self.config.ema_slow)
        atr_series = atr(frame, self.config.atr_window)

        latest_close = float(close.iloc[-1])
        latest_ema20 = float(ema20.iloc[-1])
        latest_ema50 = float(ema50.iloc[-1])
        latest_ema200 = float(ema200.iloc[-1])
        latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        avg_volume = float(volume.rolling(self.config.volume_sma_window).mean().iloc[-1])
        current_volume = float(volume.iloc[-1])
        avg_turnover = float((close * volume).rolling(self.config.volume_sma_window).mean().iloc[-1])
        recent_high_20d = float(close.tail(20).max())
        recent_high_40d = float(close.tail(40).max())
        recent_low_20d = float(close.tail(20).min())
        days_in_consolidation = int((close.tail(40).diff().abs() < (close.tail(40).std() * 0.5)).sum())
        higher_highs = bool(high.tail(3).dropna().is_monotonic_increasing)
        higher_lows = bool(low.tail(3).dropna().is_monotonic_increasing)
        trend_template_pass = bool(latest_close > latest_ema20 and latest_ema20 > latest_ema50 > latest_ema200)
        relative_strength = 0.0
        if latest_close > recent_low_20d * 1.03:
            relative_strength += 50.0
        if latest_close > latest_ema20:
            relative_strength += 50.0

        sector_strength = 0.0
        if sector != "Unknown" and self.benchmark is not None and not self.benchmark.empty:
            sector_strength, _ = calculate_sector_score(frame, self.benchmark, self.config, ticker=ticker, sector_map={ticker: sector})

        market_regime = str(self.market_regime_snapshot.get("regime", "UNKNOWN"))
        market_regime_score = float(self.market_regime_snapshot.get("score", 0.0) or 0.0)

        if self.config.quality_min_market_cap_cr > 0 or self.config.quality_max_market_cap_cr > 0:
            market_cap_cr = get_market_cap_cr_quietly(ticker)
        else:
            market_cap_cr = 0.0
        market_cap_mode = str(self.config.quality_market_cap_mode or "Custom")

        context = QualityContext(
            ticker=ticker,
            sector=sector,
            config=self.config,
            frame=frame,
            close=close,
            high=high,
            low=low,
            open=open_,
            volume=volume,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            atr=atr_series,
            latest_close=latest_close,
            latest_ema20=latest_ema20,
            latest_ema50=latest_ema50,
            latest_ema200=latest_ema200,
            latest_atr=latest_atr,
            avg_volume=avg_volume,
            current_volume=current_volume,
            avg_turnover=avg_turnover,
            recent_high_20d=recent_high_20d,
            recent_high_40d=recent_high_40d,
            recent_low_20d=recent_low_20d,
            days_in_consolidation=days_in_consolidation,
            higher_highs=higher_highs,
            higher_lows=higher_lows,
            trend_template_pass=trend_template_pass,
            relative_strength=relative_strength,
            sector_strength=sector_strength,
            market_regime=market_regime,
            market_regime_score=market_regime_score,
            market_cap_cr=market_cap_cr,
            market_cap_mode=market_cap_mode,
            market_cap_custom_symbols=self.config.quality_market_cap_custom_symbols,
        )
        self._context_cache[cache_key] = context
        return context

    def evaluate(self, context: QualityContext) -> QualityResult:
        if not self.config.quality_filter_enabled:
            return QualityResult(
                passed=True,
                rejection_reason="",
                failed_checks=[],
                passed_checks=["quality_filter_disabled"],
                details={"quality_filter": "disabled"},
            )

        failed_checks: List[str] = []
        passed_checks: List[str] = []
        details = {}

        for gate in self.gates:
            result = gate.evaluate(context)
            details[gate.name] = result.detail
            if result.passed:
                label = result.reason or gate.name
                passed_checks.append(label)
            else:
                failed_checks.append(result.reason or gate.name)

        if failed_checks:
            rejection_reason = "; ".join(failed_checks)
            logger.warning(
                "Quality rejection ticker=%s sector=%s failed_checks=%s",
                context.ticker,
                context.sector,
                failed_checks,
            )
            return QualityResult(
                passed=False,
                rejection_reason=rejection_reason,
                failed_checks=failed_checks,
                passed_checks=passed_checks,
                details=details,
            )

        return QualityResult(
            passed=True,
            rejection_reason="",
            failed_checks=[],
            passed_checks=passed_checks,
            details=details,
        )
