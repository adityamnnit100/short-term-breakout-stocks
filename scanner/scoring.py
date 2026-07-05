"""Final scoring and ranking for the momentum scanner."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .config import ScannerConfig


def combine_scores(trend_score: float, structure_score: float, volume_score: float, rs_score: float, sector_score: float, risk_score: float, config: ScannerConfig) -> Tuple[float, Dict[str, float]]:
    """Combine module scores into a final weighted score."""
    weighted = (
        trend_score * config.trend_weight
        + structure_score * config.structure_weight
        + volume_score * config.volume_weight
        + rs_score * config.rs_weight
        + sector_score * config.sector_weight
        + risk_score * config.risk_weight
        + 0.0 * config.reserved_weight
    )
    total = round(weighted, 2)
    return total, {
        "trend": round(trend_score, 2),
        "structure": round(structure_score, 2),
        "volume": round(volume_score, 2),
        "rs": round(rs_score, 2),
        "sector": round(sector_score, 2),
        "risk": round(risk_score, 2),
        "total": round(total, 2),
    }


def rank_candidates(rows: List[Dict[str, object]], config: ScannerConfig) -> pd.DataFrame:
    """Create a ranked scan output table."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values(["Total Score", "Trend Score"], ascending=[False, False]).head(config.max_candidates)
    return df.reset_index(drop=True)
