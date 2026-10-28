"""Pull regional revenue, total revenue and guidance out of a Netflix earnings letter.

The letter (8-K Exhibit 99.1) has two tables this module reads:

* the summary table: a header row of quarters ending in "Q4'26 Forecast",
  then a "Revenue" row with one value per quarter;
* the "Regional Breakdown" table: a header row of quarters, then for each
  region a label row ("UCAN:") followed by a "Revenue" row.

SEC HTML often splits a "$" or a "%" into its own cell, uses curly
apostrophes, and pads rows with empty cells, so every step here is written
to tolerate that. When something doesn't look right the parser raises
ParseError instead of guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import html as lxml_html

QUARTER_RE = re.compile(r"Q([1-4])\s*['’‘`]?\s*(\d{2})\b")
REGION_LABEL_RE = re.compile(r"^([A-Z]{3,6}):?$")
NUMBER_RE = re.compile(r"^\(?-?\$?\s*([\d,]+(?:\.\d+)?)\s*\)?$")


class ParseError(Exception):
    """The letter didn't have the shape we expect."""


@dataclass
class Letter:
    quarters: list[str]                      # reported quarters, oldest first
    regions: dict[str, list[float]]          # region -> revenue per quarter ($M)
    totals: dict[str, float]                 # quarter -> reported total revenue ($M)
    guidance: dict[str, float] = field(default_factory=dict)  # quarter -> forecast ($M)


def normalize_quarter(text: str) -> str | None:
    m = QUARTER_RE.search(text)
    return f"Q{m.group(1)}'{m.group(2)}" if m else None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _table_rows(table) -> list[list[str]]:
    rows = []
    for tr in table.iter("tr"):
        cells = [_clean(td.text_content()) for td in tr if td.tag in ("td", "th")]
        if any(cells):
            rows.append(cells)
    return rows


def _numbers(cells: list[str]) -> list[float]:
    """Numbers in a row, after the label. "$" and "%" cells are skipped."""
    out = []
    for c in cells:
        c = c.replace("$", "").replace("%", "").strip()
        if not c or c in ("-", "\u2014", "\u2013"):
            continue
        m = NUMBER_RE.match(c)
        if not m:
            continue
        value = float(m.group(1).replace(",", ""))
        out.append(-value if c.startswith("(") else value)
    return out


def _header_quarters(row: list[str]) -> tuple[list[str], bool]:
    joined = " ".join(row)
    quarters = [f"Q{a}'{b}" for a, b in QUARTER_RE.findall(joined)]
    has_forecast = "forecast" in joined.lower()
    return quarters, has_forecast


def _find_header(rows: list[list[str]]) -> tuple[int, list[str], bool]:
    for i, row in enumerate(rows):
        quarters, has_forecast = _header_quarters(row)
        if len(quarters) >= 3:
            return i, quarters, has_forecast
    raise ParseError("no header row with quarter labels")


def _region_label(row: list[str]) -> str | None:
    """'UCAN:' (or 'UCAN') on a row with no numbers is a region heading."""
    m = REGION_LABEL_RE.match(row[0]) if row else None
    if m and not _numbers(row[1:]):
        return m.group(1)
    return None


def _is_regional_table(rows: list[list[str]]) -> bool:
    return sum(1 for r in rows if _region_label(r)) >= 2


def _is_summary_table(rows: list[list[str]]) -> bool:
    try:
        _, _, has_forecast = _find_header(rows)
    except ParseError:
        return False
    return has_forecast and any(r and r[0].lower() == "revenue" for r in rows)


def parse_regional(rows: list[list[str]]) -> tuple[list[str], dict[str, list[float]]]:
    start, quarters, _ = _find_header(rows)
    regions: dict[str, list[float]] = {}
    current = None
    for row in rows[start + 1:]:
        label = row[0]
        region = _region_label(row)
        if region:
            current = region
            continue
        if current and label.lower() == "revenue":
            values = _numbers(row[1:])
            if len(values) != len(quarters):
                raise ParseError(
                    f"{current} revenue row has {len(values)} values for {len(quarters)} quarters"
                )
            regions[current] = values
            current = None
    if not regions:
        raise ParseError("regional table had no revenue rows")
    return quarters, regions


def parse_summary(rows: list[list[str]]) -> tuple[dict[str, float], dict[str, float]]:
    start, quarters, has_forecast = _find_header(rows)
    for row in rows[start + 1:]:
        if row[0].lower() == "revenue":
            values = _numbers(row[1:])
            if len(values) != len(quarters):
                raise ParseError(
                    f"summary revenue row has {len(values)} values for {len(quarters)} quarters"
                )
            actual_q = quarters[:-1] if has_forecast else quarters
            totals = dict(zip(actual_q, values))
            guidance = {quarters[-1]: values[-1]} if has_forecast else {}
            return totals, guidance
    raise ParseError("summary table had no revenue row")


def parse_letter(page: str | bytes) -> Letter:
    doc = lxml_html.fromstring(page)
    regional = summary = None
    for table in doc.iter("table"):
        rows = _table_rows(table)
        if regional is None and _is_regional_table(rows):
            regional = rows
        elif summary is None and _is_summary_table(rows):
            summary = rows
    if regional is None:
        raise ParseError("couldn't find the Regional Breakdown table")
    if summary is None:
        raise ParseError("couldn't find the summary table with a forecast column")

    quarters, regions = parse_regional(regional)
    totals, guidance = parse_summary(summary)
    missing = [q for q in quarters if q not in totals]
    if missing:
        raise ParseError(f"summary table is missing totals for {missing}")
    return Letter(quarters=quarters, regions=regions, totals=totals, guidance=guidance)
