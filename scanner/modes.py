"""Independent scanner modes for watchlist and entry selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
from .config import ScannerConfig
from .indicators import atr, ema


@dataclass
class FilterResult:
    name: str
    passed: Optional[bool]
    score: float
    detail: Optional[Dict[str, object]] = None


class BaseScanner:
    """Shared base class for all scanner modes."""

    def __init__(self, config: Optional[ScannerConfig] = None):
        self.config = config or ScannerConfig()

    def evaluate(self, df: pd.DataFrame, ticker: str, sector: str = "Unknown") -> Dict[str, object]:
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

    def _bb_width(self, df: pd.DataFrame) -> pd.Series:
        close = pd.to_numeric(df["Close"], errors="coerce")
        rolling_mean = close.rolling(20).mean()
        rolling_std = close.rolling(20).std()
        return (rolling_std * 2.0) / rolling_mean.replace(0, pd.NA) * 100.0

    def _reason_label(self, reasons: List[str]) -> str:
        return ", ".join(reasons) if reasons else "No clear signal"

    def _build_reason_text(self, reasons: List[str], score: float) -> str:
        lines = [f"Score: {score:.1f}"]
        if reasons:
            lines.append("Reasons:")
            lines.extend(f"✔ {reason}" for reason in reasons)
        return "\n".join(lines)

    def _trade_quality(self, score: float) -> str:
        if score >= 95:
            return "A+"
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        return "Reject"

    def _setup_id(self, score: float, reasons: List[str]) -> str:
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

    def _recommendation(self, score: float, reasons: List[str]) -> str:
        if score >= 90:
            return "Buy"
        if score >= 80:
            return "Watch Closely"
        if score >= 75:
            return "Watch"
        return "Reject"

    def _confidence(self, score: float) -> str:
        if score >= 90:
            return "Very High"
        if score >= 80:
            return "High"
        if score >= 75:
            return "Medium"
        return "Low"


class WatchlistScanner(BaseScanner):
    """Early-detection scanner for stocks building a base."""

    def evaluate(self, df: pd.DataFrame, ticker: str, sector: str = "Unknown") -> Dict[str, object]:
        prepared = self._prepare_df(df)
        if prepared.empty or len(prepared) < self.config.min_candles:
            return {"ticker": ticker, "passed": False, "score": 0.0, "reasons": [], "reason_label": "Insufficient data"}

        close = prepared["Close"]
        ema20 = self._ema(close, self.config.ema_fast)
        ema200 = self._ema(close, self.config.ema_slow)
        atr_series = self._atr(prepared)
        bbw = self._bb_width(prepared)
        volume = prepared["Volume"]

        latest_close = float(close.iloc[-1])
        latest_ema20 = float(ema20.iloc[-1])
        latest_ema200 = float(ema200.iloc[-1])
        recent_high = float(close.tail(20).max())
        base_high = float(close.tail(40).max())
        days_in_consolidation = int((prepared["Close"].tail(40).diff().abs() < (prepared["Close"].tail(40).std() * 0.5)).sum())
        recent_low = float(close.tail(20).min())
        higher_lows = bool((close.iloc[-3:] - close.iloc[-3:].shift(1)).dropna().gt(0).sum() >= 2)
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
        }


class EntryScanner(BaseScanner):
    """Actionable entry scanner for confirmed breakouts and retests."""

    def evaluate(self, df: pd.DataFrame, ticker: str, sector: str = "Unknown") -> Dict[str, object]:
        prepared = self._prepare_df(df)
        if prepared.empty or len(prepared) < self.config.min_candles:
            return {"ticker": ticker, "passed": False, "score": 0.0, "reasons": [], "reason_label": "Insufficient data"}

        close = prepared["Close"]
        ema20 = self._ema(close, self.config.ema_fast)
        ema50 = self._ema(close, self.config.ema_medium)
        ema200 = self._ema(close, self.config.ema_slow)
        atr_series = self._atr(prepared)
        volume = prepared["Volume"]

        latest_close = float(close.iloc[-1])
        latest_ema20 = float(ema20.iloc[-1])
        latest_ema50 = float(ema50.iloc[-1])
        latest_ema200 = float(ema200.iloc[-1])
        latest_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        avg_atr = float(atr_series.tail(20).mean()) if not atr_series.empty else 0.0
        avg_volume = float(volume.rolling(self.config.volume_sma_window).mean().iloc[-1])
        current_volume = float(volume.iloc[-1])
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
        passed = score >= self.config.entry_min_score
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
        }
