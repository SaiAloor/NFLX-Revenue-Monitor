"""Analysis: reconciliation, unusual quarters, forecast, backtest, guidance accuracy."""
from __future__ import annotations

import pandas as pd

from .checks import KNOWN_RECON_GAPS, RECON_TOLERANCE_MUSD, REGIONS, quarter_index

Z_LIMIT = 1.5


def next_quarter(q: str) -> str:
    i = quarter_index(q) + 1
    return f"Q{i % 4 + 1}'{(i // 4) % 100:02d}"


def reconciliation(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["quarter"]].copy()
    out["region_sum"] = df[REGIONS].sum(axis=1)
    out["reported_total"] = df["total"]
    out["difference"] = out["reported_total"] - out["region_sum"]
    out["status"] = [
        "match" if abs(d) <= RECON_TOLERANCE_MUSD else ("explained" if q in KNOWN_RECON_GAPS else "MISMATCH")
        for q, d in zip(out["quarter"], out["difference"])
    ]
    out["note"] = [KNOWN_RECON_GAPS.get(q, "") if s == "explained" else "" for q, s in zip(out["quarter"], out["status"])]
    return out


def unusual_quarters(df: pd.DataFrame, z_limit: float = Z_LIMIT) -> pd.DataFrame:
    """Quarter-over-quarter growth per region, flagged by z-score within that region."""
    qoq = df.set_index("quarter")[REGIONS].pct_change().dropna()
    z = (qoq - qoq.mean()) / qoq.std()
    rows = [
        {"quarter": q, "region": r, "qoq_growth_pct": round(qoq.loc[q, r] * 100, 1), "z_score": round(z.loc[q, r], 2)}
        for q in z.index for r in REGIONS if abs(z.loc[q, r]) >= z_limit
    ]
    out = pd.DataFrame(rows, columns=["quarter", "region", "qoq_growth_pct", "z_score"])
    return out.sort_values("z_score", key=abs, ascending=False).reset_index(drop=True)


def forecast_region(series: pd.Series, pos: int) -> float:
    """Forecast position `pos` from data strictly before it.

    Same quarter last year, grown by the average year-over-year growth of the
    two most recent quarters. Using last year's quarter as the base keeps
    seasonality in the forecast.
    """
    if pos < 6:
        raise ValueError("need six quarters of history")
    g1 = series.iloc[pos - 1] / series.iloc[pos - 5]
    g2 = series.iloc[pos - 2] / series.iloc[pos - 6]
    return series.iloc[pos - 4] * (g1 + g2) / 2


def forecast_next(df: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    target = next_quarter(df["quarter"].iloc[-1])
    pos = len(df)
    rows = []
    for r in REGIONS:
        s = df[r].reset_index(drop=True)
        base = s.iloc[pos - 4]
        fc = forecast_region(s, pos)
        rows.append({"region": r, "base_quarter": df["quarter"].iloc[pos - 4], "base_musd": int(base),
                     "growth_used_pct": round((fc / base - 1) * 100, 1), "forecast_musd": int(round(fc))})
    out = pd.DataFrame(rows)
    total_base, total_fc = out["base_musd"].sum(), out["forecast_musd"].sum()
    out.loc[len(out)] = {"region": "Total", "base_quarter": out["base_quarter"].iloc[0], "base_musd": int(total_base),
                         "growth_used_pct": round((total_fc / total_base - 1) * 100, 1), "forecast_musd": int(total_fc)}
    return target, out


def backtest(df: pd.DataFrame) -> pd.DataFrame:
    """Re-run the forecast for every past quarter it could have been made for."""
    rows = []
    for pos in range(6, len(df)):
        fc = sum(forecast_region(df[r].reset_index(drop=True), pos) for r in REGIONS)
        actual = sum(df[r].iloc[pos] for r in REGIONS)
        rows.append({"quarter": df["quarter"].iloc[pos], "forecast_musd": int(round(fc)),
                     "actual_musd": int(actual), "error_pct": round((fc / actual - 1) * 100, 2)})
    return pd.DataFrame(rows, columns=["quarter", "forecast_musd", "actual_musd", "error_pct"])


def guidance_accuracy(df: pd.DataFrame, guidance: pd.DataFrame) -> pd.DataFrame:
    actual = df.set_index("quarter")["total"]
    out = guidance[["quarter", "guidance_musd", "issued_in"]].copy()
    out["actual_musd"] = [actual.get(q) for q in out["quarter"]]
    out["error_pct"] = [
        round((g / a - 1) * 100, 2) if pd.notna(a) else None for g, a in zip(out["guidance_musd"], out["actual_musd"])
    ]
    return out
