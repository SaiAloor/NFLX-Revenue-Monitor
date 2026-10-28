"""Data quality checks run before anything is saved.

An "error" stops the update so bad numbers never reach the dataset; a
"warning" is saved to the run log and shown in the report.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

REGIONS = ["UCAN", "EMEA", "LATAM", "APAC"]

# Rounding in the letters leaves regions and total up to $1M apart.
RECON_TOLERANCE_MUSD = 2
# Known, explained gaps between the regions and the reported total.
KNOWN_RECON_GAPS = {
    "Q3'23": "most likely DVD revenue, which sat outside the four streaming regions until the DVD business closed in Sep 2023",
}
# A region moving more than this in one quarter is worth a second look.
MAX_QOQ_CHANGE = 0.20


@dataclass
class Issue:
    level: str      # "error" or "warning"
    check: str
    message: str

    def as_dict(self) -> dict:
        return {"level": self.level, "check": self.check, "message": self.message}


def quarter_index(q: str) -> int:
    """Q3'26 -> a running number, so consecutive quarters differ by 1."""
    return (2000 + int(q[3:])) * 4 + int(q[1]) - 1


def check_regions(df: pd.DataFrame) -> list[Issue]:
    missing = [r for r in REGIONS if r not in df.columns]
    extra = [c for c in df.columns if c not in REGIONS + ["quarter", "period_end", "total"]]
    issues = []
    if missing:
        issues.append(Issue("error", "regions", f"regions missing from the letter: {missing}"))
    if extra:
        issues.append(Issue("error", "regions", f"new regions in the letter, update REGIONS: {extra}"))
    return issues


def check_continuity(df: pd.DataFrame) -> list[Issue]:
    idx = [quarter_index(q) for q in df["quarter"]]
    gaps = [
        f"{a} -> {b}" for (a, ia), (b, ib) in zip(zip(df["quarter"], idx), zip(df["quarter"][1:], idx[1:]))
        if ib - ia != 1
    ]
    return [Issue("error", "continuity", f"quarters are not consecutive: {gaps}")] if gaps else []


def check_reconciliation(df: pd.DataFrame) -> list[Issue]:
    issues = []
    for _, row in df.iterrows():
        diff = row["total"] - sum(row[r] for r in REGIONS)
        if abs(diff) <= RECON_TOLERANCE_MUSD:
            continue
        if row["quarter"] in KNOWN_RECON_GAPS:
            continue
        issues.append(Issue(
            "error", "reconciliation",
            f"{row['quarter']}: regions sum to {sum(row[r] for r in REGIONS):,.0f} "
            f"but the reported total is {row['total']:,.0f} (gap {diff:+,.0f})",
        ))
    return issues


def check_plausibility(df: pd.DataFrame) -> list[Issue]:
    issues = []
    for r in REGIONS:
        change = df[r].pct_change()
        for q, c in zip(df["quarter"], change):
            if pd.notna(c) and abs(c) > MAX_QOQ_CHANGE:
                issues.append(Issue("warning", "plausibility", f"{r} moved {c:+.1%} in {q}; check the source"))
        if (df[r] <= 0).any():
            issues.append(Issue("error", "plausibility", f"{r} has a zero or negative revenue value"))
    return issues


def check_restatements(old: pd.DataFrame, new_rows: pd.DataFrame) -> list[Issue]:
    """Quarters that appear in both, with different numbers."""
    issues = []
    merged = old.merge(new_rows, on="quarter", suffixes=("_old", "_new"))
    for _, row in merged.iterrows():
        for col in REGIONS + ["total"]:
            a, b = row[f"{col}_old"], row[f"{col}_new"]
            if abs(a - b) > 1:
                issues.append(Issue(
                    "warning", "restatement",
                    f"{row['quarter']} {col} changed from {a:,.0f} to {b:,.0f}; keeping the newer letter's figure",
                ))
    return issues


def run_all(df: pd.DataFrame) -> list[Issue]:
    return check_regions(df) + check_continuity(df) + check_reconciliation(df) + check_plausibility(df)
