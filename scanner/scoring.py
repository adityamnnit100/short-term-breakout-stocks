"""Final scoring and ranking for the momentum scanner."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from .config import ScannerConfig


def combine_scores(trend_score: float, structure_score: float, volume_score: float, rs_score: float, sector_score: float, risk_score: float, config: ScannerConfig) -> Tuple[float, Dict[str, float]]:
    """Combine module scores into a final weighted score."""
    # Use getattr with safe defaults so this helper is robust across config shapes.
    t_w = float(getattr(config, "trend_weight", 0.0) or 0.0)
    s_w = float(getattr(config, "structure_weight", 0.0) or 0.0)
    v_w = float(getattr(config, "volume_weight", 0.0) or 0.0)
    rs_w = float(getattr(config, "rs_weight", 0.0) or 0.0)
    sec_w = float(getattr(config, "sector_weight", 0.0) or 0.0)
    r_w = float(getattr(config, "risk_weight", 0.0) or 0.0)
    reserved_w = float(getattr(config, "reserved_weight", 0.0) or 0.0)

    weighted = (
        trend_score * t_w
        + structure_score * s_w
        + volume_score * v_w
        + rs_score * rs_w
        + sector_score * sec_w
        + risk_score * r_w
        + 0.0 * reserved_w
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
