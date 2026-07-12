"""Breakout Readiness Engine orchestration."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from .breakout_score import aggregate_breakout_readiness, score_breakout_pressure
from .candle_tightness import score_candle_tightness
from .compression import score_compression
from .models import BreakoutReadyResult, ScanResult
from .resistance import score_breakout_distance
from .rs_acceleration import score_rs_acceleration
from .volume import score_volume_dryup


def _row_price(row: pd.Series) -> float:
    for key in ("LTP", "Entry Price", "Close", "Price", "current_price"):
        if key in row and pd.notna(row.get(key)):
            try:
                return float(row.get(key))
            except Exception:
                continue
    return 0.0


def scan_results_to_candidates(results: pd.DataFrame) -> List[ScanResult]:
    """Normalize scanner output rows into input models for the readiness engine."""
    if results is None or results.empty or "Ticker" not in results.columns:
        return []

    candidates: List[ScanResult] = []
    for _, row in results.iterrows():
        ticker = str(row.get("Ticker", "")).strip()
        if not ticker:
            continue
        candidates.append(
            ScanResult(
                ticker=ticker,
                current_price=_row_price(row),
                sector=str(row.get("Sector", "Unknown") or "Unknown"),
                scanner_type=str(row.get("Type") or row.get("Scanner Type") or "") or None,
                universe=str(row.get("Universe") or "") or None,
                source_row=row.to_dict(),
            )
        )
    return candidates


def _history_from_loader(loader: Callable[..., pd.DataFrame], ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    try:
        df = loader(ticker, period=period, interval=interval)
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def rank_breakout_readiness(
    results: pd.DataFrame,
    history_loader: Callable[..., pd.DataFrame],
    benchmark_loader: Optional[Callable[..., pd.DataFrame]] = None,
    max_candidates: int = 8,
    min_score: float = 45.0,
) -> pd.DataFrame:
    """Rank scanner candidates by breakout readiness."""
    candidates = scan_results_to_candidates(results)
    if not candidates:
        return pd.DataFrame()

    benchmark = None
    if benchmark_loader is not None:
        try:
            benchmark = benchmark_loader(period="6mo")
        except Exception:
            benchmark = None

    ready_rows: List[Dict[str, object]] = []
    for candidate in candidates:
        history = _history_from_loader(history_loader, candidate.ticker, period="1y", interval="1d")
        if history is None or history.empty or len(history) < 30:
            continue

        current_price = candidate.current_price or float(pd.to_numeric(history["Close"], errors="coerce").dropna().iloc[-1])
        compression_score, compression_metrics = score_compression(history)
        breakout_distance_score, resistance_metrics = score_breakout_distance(history, current_price)
        volume_dryup_score, volume_metrics = score_volume_dryup(history)
        candle_tightness_score, candle_metrics = score_candle_tightness(history)
        rs_acceleration_score, rs_metrics = score_rs_acceleration(history, benchmark)
        breakout_pressure_score, pressure_metrics = score_breakout_pressure(history)

        readiness_score, confluence_bonus = aggregate_breakout_readiness(
            compression_score,
            breakout_distance_score,
            volume_dryup_score,
            candle_tightness_score,
            rs_acceleration_score,
            breakout_pressure_score,
        )

        if readiness_score < min_score:
            continue

        nearest_resistance = float(resistance_metrics.get("nearest_resistance", 0.0) or 0.0)
        resistance_gap_pct = float(resistance_metrics.get("resistance_gap_pct", 0.0) or 0.0)
        reasons = []
        if resistance_gap_pct <= 3:
            reasons.append("Near resistance")
        if float(compression_metrics.get("atr_contraction_pct", 0.0) or 0.0) <= -5:
            reasons.append("Volatility compressing")
        if float(volume_metrics.get("volume_avg3", 0.0) or 0.0) < float(volume_metrics.get("volume_avg20", 0.0) or 0.0):
            reasons.append("Volume drying up")
        if float(candle_metrics.get("nr7", 0.0) or 0.0):
            reasons.append("NR7")
        if float(pressure_metrics.get("ascending_triangle", 0.0) or 0.0):
            reasons.append("Ascending triangle")

        ready_rows.append(
            BreakoutReadyResult(
                ticker=candidate.ticker,
                breakout_readiness_score=readiness_score,
                current_price=round(float(current_price), 2),
                nearest_resistance=round(nearest_resistance, 2),
                resistance_gap_pct=round(resistance_gap_pct, 2),
                compression_score=compression_score,
                breakout_distance_score=breakout_distance_score,
                volume_dryup_score=volume_dryup_score,
                candle_tightness_score=candle_tightness_score,
                rs_acceleration_score=rs_acceleration_score,
                breakout_pressure_score=breakout_pressure_score,
                confluence_bonus=confluence_bonus,
                sector=candidate.sector,
                reasons=tuple(reasons),
                metrics={
                    "compression": compression_metrics,
                    "resistance": resistance_metrics,
                    "volume": volume_metrics,
                    "candle": candle_metrics,
                    "rs": rs_metrics,
                    "pressure": pressure_metrics,
                },
            ).to_dict()
        )

    if not ready_rows:
        return pd.DataFrame()

    ranked = pd.DataFrame(ready_rows).sort_values("breakout_readiness_score", ascending=False)
    return ranked.head(max_candidates).reset_index(drop=True)
