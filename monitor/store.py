"""Reading, merging and saving the dataset in data/."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .checks import REGIONS, quarter_index
from .parse import Letter

DATA = Path(__file__).resolve().parent.parent / "data"
REVENUE_CSV = DATA / "revenue_by_region.csv"
GUIDANCE_CSV = DATA / "guidance_history.csv"
PROCESSED_JSON = DATA / "processed_filings.json"

QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def period_end(q: str) -> str:
    return f"20{q[3:]}-{QUARTER_END[int(q[1])]}"


def load_revenue(path: Path = REVENUE_CSV) -> pd.DataFrame:
    return pd.read_csv(path)


def load_guidance(path: Path = GUIDANCE_CSV) -> pd.DataFrame:
    return pd.read_csv(path)


def load_processed(path: Path = PROCESSED_JSON) -> set[str]:
    return set(json.loads(path.read_text())["processed"]) if path.exists() else set()


def letter_to_frame(letter: Letter) -> pd.DataFrame:
    rows = []
    for i, q in enumerate(letter.quarters):
        row = {"quarter": q, "period_end": period_end(q)}
        row.update({r: int(round(v[i])) for r, v in letter.regions.items()})
        row["total"] = int(round(letter.totals[q]))
        rows.append(row)
    cols = ["quarter", "period_end"] + [r for r in REGIONS if r in letter.regions] + \
        [r for r in letter.regions if r not in REGIONS] + ["total"]
    return pd.DataFrame(rows)[cols]


def merge(old: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    """Add new quarters; for overlapping quarters the newer letter wins."""
    combined = pd.concat([old[~old["quarter"].isin(new_rows["quarter"])], new_rows], ignore_index=True)
    combined["_i"] = combined["quarter"].map(quarter_index)
    return combined.sort_values("_i").drop(columns="_i").reset_index(drop=True)


def merge_guidance(old: pd.DataFrame, letter: Letter, issued_in: str, accession: str) -> pd.DataFrame:
    new = pd.DataFrame([
        {"quarter": q, "guidance_musd": int(round(v)), "issued_in": issued_in, "accession": accession}
        for q, v in letter.guidance.items()
    ])
    if new.empty:
        return old
    combined = pd.concat([old[~old["quarter"].isin(new["quarter"])], new], ignore_index=True)
    combined["_i"] = combined["quarter"].map(quarter_index)
    return combined.sort_values("_i").drop(columns="_i").reset_index(drop=True)


def save(revenue: pd.DataFrame, guidance: pd.DataFrame, processed: set[str]) -> None:
    revenue.to_csv(REVENUE_CSV, index=False)
    guidance.to_csv(GUIDANCE_CSV, index=False)
    PROCESSED_JSON.write_text(json.dumps({"processed": sorted(processed)}, indent=2) + "\n")
