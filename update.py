"""Check SEC EDGAR for new Netflix earnings letters, update the data, rebuild the report.

    python update.py                 # check EDGAR, add any new letters, rebuild
    python update.py --offline       # rebuild from the data already in data/
    python update.py --letter FILE   # parse a saved letter (HTML) instead of EDGAR

Exit codes: 0 = done (with or without new data), 1 = a check failed and nothing was saved.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from monitor import checks, model, report, store
from monitor.parse import ParseError, parse_letter


def accession_key(acc: str) -> tuple[int, int]:
    """0001065280-26-000290 -> (26, 290): filings by the same filer sort by year, then sequence."""
    _, yy, seq = acc.split("-")
    return int(yy), int(seq)


def apply_letter(revenue, guidance, page, accession, issues):
    letter = parse_letter(page)
    new_rows = store.letter_to_frame(letter)
    issues += checks.check_restatements(revenue, new_rows)
    revenue = store.merge(revenue, new_rows)
    guidance = store.merge_guidance(guidance, letter, letter.quarters[-1], accession)
    return revenue, guidance, letter


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="don't contact EDGAR")
    ap.add_argument("--letter", type=Path, help="parse this saved letter instead of EDGAR")
    args = ap.parse_args(argv)

    revenue, guidance, processed = store.load_revenue(), store.load_guidance(), store.load_processed()
    issues: list[checks.Issue] = []
    new_filings: list[str] = []

    try:
        if args.letter:
            revenue, guidance, letter = apply_letter(revenue, guidance, args.letter.read_bytes(), args.letter.name, issues)
            new_filings.append(args.letter.name)
        elif not args.offline:
            from monitor.sec import SecClient
            sec = SecClient()
            # Only letters newer than the newest one already in the dataset.
            newest = max(map(accession_key, processed)) if processed else (0, 0)
            pending = [f for f in sec.earnings_filings() if accession_key(f.accession) > newest]
            for filing in reversed(pending):  # oldest first
                sec.find_letter(filing)
                print(f"New earnings letter: {filing.accession} ({filing.filing_date}) {filing.url}")
                revenue, guidance, letter = apply_letter(
                    revenue, guidance, sec.download(filing.url), filing.accession, issues)
                processed.add(filing.accession)
                new_filings.append(filing.accession)
    except ParseError as e:
        print(f"ERROR: couldn't read the earnings letter: {e}", file=sys.stderr)
        return 1

    issues += checks.run_all(revenue)
    errors = [i for i in issues if i.level == "error"]
    for i in issues:
        print(f"{i.level.upper()} [{i.check}] {i.message}", file=sys.stderr if i.level == "error" else sys.stdout)
    if errors:
        print("Nothing saved because a check failed.", file=sys.stderr)
        return 1

    if new_filings:
        store.save(revenue, guidance, processed)

    target, fc = model.forecast_next(revenue)
    summary = report.build(
        revenue, guidance,
        recon=model.reconciliation(revenue),
        unusual=model.unusual_quarters(revenue),
        target=target, fc=fc,
        bt=model.backtest(revenue),
        gacc=model.guidance_accuracy(revenue, guidance),
        issues=issues, new_filings=new_filings,
    )
    print(f"{summary['latest_quarter']} revenue ${summary['latest_total_musd']:,}M; "
          f"{target} forecast ${summary['forecast_total_musd']:,}M"
          + (f" vs guidance ${summary['guidance_musd']:,}M ({summary['model_vs_guidance_pct']:+.1f}%)"
             if summary["guidance_musd"] else "")
          + f"; backtest error {summary['backtest_mape_pct']:.2f}%")
    print("New filings: " + (", ".join(new_filings) if new_filings else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
