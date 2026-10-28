"""Write outputs/, the README results block, and the GitHub Pages site in docs/."""
from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .checks import REGIONS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
DOCS = ROOT / "docs"
README = ROOT / "README.md"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"

COLORS = {"UCAN": "#2b6cb0", "EMEA": "#c05621", "LATAM": "#2f855a", "APAC": "#9b2c2c"}


def _style(ax):
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", rotation=45)


def chart_regions(df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 4.5))
    last = df.iloc[-1]
    offsets = {}
    ends = sorted(REGIONS, key=lambda r: last[r])
    for a, b in zip(ends, ends[1:]):  # keep end labels apart
        if abs(last[b] - last[a]) < 0.05 * df[REGIONS].max().max():
            offsets[a], offsets[b] = -6, 6
    for r in REGIONS:
        ax.plot(df["quarter"], df[r], marker="o", markersize=3, linewidth=2, color=COLORS[r])
        ax.annotate(f"{r} {last[r]:,.0f}", (len(df) - 1, last[r]), xytext=(6, offsets.get(r, 0)),
                    textcoords="offset points", va="center", fontsize=9, color=COLORS[r])
    ax.set_title("Revenue by region (US$ millions)", loc="left")
    ax.set_ylim(0)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_forecast(df: pd.DataFrame, bt: pd.DataFrame, target: str, fc_total: int,
                   guidance: dict[str, int], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 4.5))
    x = list(df["quarter"]) + [target]
    actual = df[REGIONS].sum(axis=1).tolist()
    ax.plot(x[:-1], actual, linewidth=2, color="#1a202c", label="Actual (sum of regions)")
    ax.scatter(bt["quarter"], bt["forecast_musd"], s=28, color="#c05621", zorder=3,
               label="Model forecast, made one quarter ahead")
    ax.scatter([target], [fc_total], s=60, marker="D", color="#c05621", zorder=3, label=f"Model forecast, {target}")
    if target in guidance:
        ax.scatter([target], [guidance[target]], s=60, marker="s", color="#2b6cb0", zorder=3,
                   label=f"Netflix guidance, {target}")
    ax.set_title("Forecast vs actual, total revenue (US$ millions)", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _md_table(df: pd.DataFrame, headers: dict[str, str], fmt: dict[str, str]) -> str:
    cols = list(headers)
    lines = ["| " + " | ".join(headers[c] for c in cols) + " |",
             "| " + " | ".join("---:" if c in fmt else "---" for c in cols) + " |"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            cells.append("" if pd.isna(v) else (format(v, fmt[c]) if c in fmt else str(v)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build(df, guidance_hist, recon, unusual, target, fc, bt, gacc, issues, new_filings):
    OUT.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    recon.to_csv(OUT / "reconciliation.csv", index=False)
    unusual.to_csv(OUT / "unusual_quarters.csv", index=False)
    fc.to_csv(OUT / "forecast_next_quarter.csv", index=False)
    bt.to_csv(OUT / "backtest.csv", index=False)
    gacc.to_csv(OUT / "guidance_accuracy.csv", index=False)

    guidance = dict(zip(guidance_hist["quarter"], guidance_hist["guidance_musd"]))
    fc_total = int(fc.loc[fc["region"] == "Total", "forecast_musd"].iloc[0])
    chart_regions(df, OUT / "revenue_by_region.png")
    chart_forecast(df, bt, target, fc_total, guidance, OUT / "forecast_vs_actual.png")

    mape = bt["error_pct"].abs().mean() if len(bt) else float("nan")
    latest = df.iloc[-1]
    prior = df[df["quarter"] == f"{latest['quarter'][:3]}{int(latest['quarter'][3:]) - 1:02d}"]
    yoy = (latest["total"] / prior["total"].iloc[0] - 1) * 100 if len(prior) else float("nan")
    g = guidance.get(target)
    gap = (fc_total / g - 1) * 100 if g else None
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    status = "All checks passed" if not issues else f"{len(errors)} errors, {len(warnings)} warnings"

    summary = {
        "checked_at": checked_at, "latest_quarter": latest["quarter"], "latest_total_musd": int(latest["total"]),
        "yoy_growth_pct": round(yoy, 1), "forecast_quarter": target, "forecast_total_musd": fc_total,
        "guidance_musd": g, "model_vs_guidance_pct": None if gap is None else round(gap, 1),
        "backtest_mape_pct": round(mape, 2), "backtest_quarters": len(bt),
        "quarters_reconciled": int((recon["status"] != "MISMATCH").sum()), "quarters_total": len(recon),
        "quarters_explained": int((recon["status"] == "explained").sum()),
        "new_filings": new_filings, "issues": [i.as_dict() for i in issues],
    }
    (OUT / "run_log.json").write_text(json.dumps(summary, indent=2) + "\n")

    headline = (f"**{latest['quarter']} revenue:** ${latest['total']:,.0f}M ({yoy:+.1f}% year over year)  \n"
                f"**{target} model forecast:** ${fc_total:,}M"
                + (f" vs Netflix guidance ${g:,}M ({gap:+.1f}%)" if g else "") + "  \n"
                f"**Backtest error:** {mape:.2f}% average absolute error over {len(bt)} quarters  \n"
                f"**Data checks:** {status} · updated {checked_at}")
    block = "\n\n".join([
        headline,
        "![Revenue by region](outputs/revenue_by_region.png)",
        "![Forecast vs actual](outputs/forecast_vs_actual.png)",
        f"**{target} forecast by region (US$ millions)**",
        _md_table(fc, {"region": "Region", "base_quarter": "Base quarter", "base_musd": "Base",
                       "growth_used_pct": "Growth used (%)", "forecast_musd": "Forecast"},
                  {"base_musd": ",", "growth_used_pct": ".1f", "forecast_musd": ","}),
        "**Unusual quarters** (quarter-over-quarter growth at least 1.5 standard deviations from that region's norm)",
        _md_table(unusual, {"quarter": "Quarter", "region": "Region", "qoq_growth_pct": "QoQ growth (%)",
                            "z_score": "Z-score"}, {"qoq_growth_pct": "+.1f", "z_score": ".2f"}),
        "**Netflix guidance vs actual**",
        _md_table(gacc, {"quarter": "Quarter", "issued_in": "Issued in", "guidance_musd": "Guidance",
                         "actual_musd": "Actual", "error_pct": "Error (%)"},
                  {"guidance_musd": ",", "actual_musd": ",.0f", "error_pct": "+.2f"}),
    ])
    text = README.read_text()
    if START in text and END in text:
        head, rest = text.split(START, 1)
        _, tail = rest.split(END, 1)
        README.write_text(f"{head}{START}\n{block}\n{END}{tail}")

    for name in ("revenue_by_region.png", "forecast_vs_actual.png"):
        shutil.copy(OUT / name, DOCS / name)
    build_site(summary, fc, unusual, gacc, recon, bt, issues)
    return summary


def _html_table(df: pd.DataFrame, headers: dict[str, str], fmt: dict[str, str]) -> str:
    th = "".join(f"<th{' class=num' if c in fmt else ''}>{html.escape(h)}</th>" for c, h in headers.items())
    body = []
    for _, row in df.iterrows():
        tds = []
        for c in headers:
            v = row[c]
            s = "" if pd.isna(v) else (format(v, fmt[c]) if c in fmt else str(v))
            tds.append(f"<td{' class=num' if c in fmt else ''}>{html.escape(s)}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f"<div class=scroll><table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def build_site(s, fc, unusual, gacc, recon, bt, issues) -> None:
    gap = "" if s["model_vs_guidance_pct"] is None else f"{s['model_vs_guidance_pct']:+.1f}%"
    tiles = [
        (f"{s['latest_quarter']} revenue", f"${s['latest_total_musd']:,}M", f"{s['yoy_growth_pct']:+.1f}% year over year"),
        (f"{s['forecast_quarter']} model forecast", f"${s['forecast_total_musd']:,}M", "Sum of four regional forecasts"),
        (f"{s['forecast_quarter']} Netflix guidance", f"${s['guidance_musd']:,}M" if s["guidance_musd"] else "n/a",
         f"Model vs guidance {gap}" if gap else "Not yet issued"),
        ("Backtest error", f"{s['backtest_mape_pct']:.2f}%", f"Average absolute error, {s['backtest_quarters']} quarters"),
        ("Data checks", f"{s['quarters_reconciled']}/{s['quarters_total']}",
         "Quarters reconciled" + (f" ({s['quarters_explained']} explained gap)" if s["quarters_explained"] else "")),
    ]
    tile_html = "".join(
        f"<div class=tile><span class=label>{html.escape(a)}</span><span class=num-big>{html.escape(b)}</span>"
        f"<span class=sub>{html.escape(c)}</span></div>" for a, b, c in tiles)
    issue_html = "".join(f"<li class={i.level}>{html.escape(i.message)}</li>" for i in issues) or \
        "<li class=ok>All checks passed: regions reconcile, quarters are consecutive, no restatements.</li>"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Netflix Regional Revenue Monitor</title>
<style>
:root{{--bg:#fbfaf8;--fg:#1a202c;--muted:#5a6270;--line:#e3e0da;--panel:#fff;--ok:#2f855a;--warn:#b7791f;--bad:#c53030}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181d;--fg:#e8e6e3;--muted:#a0a4ab;--line:#2c2f36;--panel:#1d2026}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1040px;margin:0 auto;padding:32px max(16px,env(safe-area-inset-left))}}
h1{{font-size:28px;margin:0 0 4px}} h2{{font-size:17px;margin:32px 0 8px}}
.lead{{color:var(--muted);margin:0 0 20px;max-width:70ch}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}
.tile{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:grid;gap:2px}}
.label,.sub{{font-size:12px;color:var(--muted)}} .num-big{{font-size:24px;font-variant-numeric:tabular-nums}}
img{{max-width:100%;background:#fff;border:1px solid var(--line);border-radius:8px}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}} th{{color:var(--muted);font-weight:500;font-size:12px}}
.num{{text-align:right}} ul.issues{{padding-left:18px}} li.ok{{color:var(--ok)}} li.warning{{color:var(--warn)}} li.error{{color:var(--bad)}}
footer{{color:var(--muted);font-size:13px;margin-top:40px}}
</style></head><body><main>
<h1>Netflix Regional Revenue Monitor</h1>
<p class=lead>Quarterly revenue for Netflix's four regions, pulled automatically from each earnings letter on SEC EDGAR, checked, and re-forecast. Updated {html.escape(s['checked_at'])}.</p>
<div class=tiles>{tile_html}</div>
<h2>Revenue by region</h2><img src="revenue_by_region.png" alt="Line chart of quarterly revenue by region">
<h2>Forecast vs actual</h2><img src="forecast_vs_actual.png" alt="Total revenue with one-quarter-ahead model forecasts and Netflix guidance">
<h2>{html.escape(s['forecast_quarter'])} forecast by region (US$ millions)</h2>
{_html_table(fc, {"region": "Region", "base_quarter": "Base quarter", "base_musd": "Base", "growth_used_pct": "Growth used (%)", "forecast_musd": "Forecast"}, {"base_musd": ",", "growth_used_pct": ".1f", "forecast_musd": ","})}
<h2>Unusual quarters</h2>
{_html_table(unusual, {"quarter": "Quarter", "region": "Region", "qoq_growth_pct": "QoQ growth (%)", "z_score": "Z-score"}, {"qoq_growth_pct": "+.1f", "z_score": ".2f"})}
<h2>Backtest: model forecast vs actual</h2>
{_html_table(bt, {"quarter": "Quarter", "forecast_musd": "Forecast", "actual_musd": "Actual", "error_pct": "Error (%)"}, {"forecast_musd": ",", "actual_musd": ",", "error_pct": "+.2f"})}
<h2>Netflix guidance vs actual</h2>
{_html_table(gacc, {"quarter": "Quarter", "issued_in": "Issued in", "guidance_musd": "Guidance", "actual_musd": "Actual", "error_pct": "Error (%)"}, {"guidance_musd": ",", "actual_musd": ",.0f", "error_pct": "+.2f"})}
<h2>Data checks</h2><ul class=issues>{issue_html}</ul>
{_html_table(recon, {"quarter": "Quarter", "region_sum": "Sum of regions", "reported_total": "Reported total", "difference": "Difference", "status": "Status"}, {"region_sum": ",", "reported_total": ",", "difference": "+,"})}
<footer>Source: Netflix quarterly earnings letters (Form 8-K, Exhibit 99.1) on SEC EDGAR. The forecast is a simple baseline for checking guidance, not investment advice. Built by Sai Soumya Aloor.</footer>
</main></body></html>
"""
    (DOCS / "index.html").write_text(page)
