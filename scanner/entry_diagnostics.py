"""Summarize the exported `data/entry.csv` scanner results into a compact diagnostics JSON.

Usage:
  python -m scanner.entry_diagnostics

This aggregates counts for Trigger Decision, Trade Quality, Recommendation,
and tallies failed modules and reasons where available.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger("AlphaScanner.EntryDiagnostics")


def summarize_entry_csv(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if not rows:
        raise SystemExit("No rows found in entry CSV")

    total = len(rows)
    decisions = Counter()
    qualities = Counter()
    recommendations = Counter()
    failed_modules = Counter()
    failed_reasons = Counter()

    for r in rows:
        decisions[r.get("Trigger Decision") or "Unknown"] += 1
        qualities[r.get("Trade Quality") or "Unknown"] += 1
        recommendations[r.get("Recommendation") or "Unknown"] += 1

        for col, counter in (("Trigger Failed Modules", failed_modules), ("Trigger Reasons", failed_reasons)):
            raw = r.get(col)
            if not raw:
                continue
            s = raw.strip()
            # crude split of list-like string
            if s.startswith("[") and s.endswith("]"):
                s = s[1:-1]
            parts = [p.strip().strip("'\"") for p in s.split(",") if p.strip()]
            for p in parts:
                counter[p] += 1

    top_failed_modules = failed_modules.most_common(20)
    top_failed_reasons = failed_reasons.most_common(30)

    return {
        "total_rows": total,
        "decisions": dict(decisions),
        "trade_quality": dict(qualities),
        "recommendation": dict(recommendations),
        "top_failed_modules": top_failed_modules,
        "top_failed_reasons": top_failed_reasons,
    }


def main():
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "data" / "entry.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found")

    report = summarize_entry_csv(path)
    out = repo_root / "data" / "entry_diagnostics.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote diagnostics to {out}")


if __name__ == "__main__":
    main()
