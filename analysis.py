"""Netflix regional revenue monitor.

Reads quarterly revenue by region (US$ millions) taken from Netflix shareholder
letters, then:
  1. reconciles the four regions against the reported total each quarter,
  2. flags quarters with unusual quarter-over-quarter growth per region,
  3. builds a simple Q4'26 forecast per region and compares it to guidance.

Run:  python analysis.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REGIONS = ["UCAN", "EMEA", "LATAM", "APAC"]
Z_LIMIT = 1.5          # how far from normal a quarter must be to get flagged
RECON_TOLERANCE = 1    # $M of rounding allowed between regions and total

DATA = Path("data")
OUT = Path("outputs")
OUT.mkdir(exist_ok=True)

rev = pd.read_csv(DATA / "netflix_revenue_by_region.csv", parse_dates=["period_end"])
rev = rev.sort_values("period_end").set_index("quarter")
guidance = pd.read_csv(DATA / "netflix_guidance.csv").set_index("quarter")["revenue_musd"]

# 1. Reconciliation: do the regions add up to the reported total?
recon = pd.DataFrame({
    "region_sum": rev[REGIONS].sum(axis=1),
    "reported_total": rev["total"],
})
recon["difference"] = recon["reported_total"] - recon["region_sum"]
recon["matches"] = recon["difference"].abs() <= RECON_TOLERANCE
recon.to_csv(OUT / "reconciliation.csv")

# 2. Unusual quarters: z-score of QoQ growth within each region
qoq = rev[REGIONS].pct_change().dropna()
z = (qoq - qoq.mean()) / qoq.std()
flags = (
    z.stack().rename("z_score").reset_index()
    .rename(columns={"level_1": "region"})
    .query("abs(z_score) >= @Z_LIMIT")
)
flags["qoq_growth_pct"] = [round(qoq.loc[q, r] * 100, 1) for q, r in zip(flags["quarter"], flags["region"])]
flags["z_score"] = flags["z_score"].round(2)
flags = flags.sort_values("z_score", key=abs, ascending=False)
flags.to_csv(OUT / "unusual_quarters.csv", index=False)

# 3. Forecast Q4'26: Q4'25 x average YoY growth of the last two quarters
yoy_q3 = rev.loc["Q3'26", REGIONS] / rev.loc["Q3'25", REGIONS]
yoy_q2 = rev.loc["Q2'26", REGIONS] / rev.loc["Q2'25", REGIONS]
growth = (yoy_q3 + yoy_q2) / 2
forecast = pd.DataFrame({
    "q4_25": rev.loc["Q4'25", REGIONS],
    "growth_used_pct": ((growth - 1) * 100).round(1),
    "q4_26_forecast": (rev.loc["Q4'25", REGIONS] * growth).round(0).astype(int),
})
forecast.loc["Total"] = [
    forecast["q4_25"].sum(),
    round((forecast["q4_26_forecast"].sum() / forecast["q4_25"].sum() - 1) * 100, 1),
    forecast["q4_26_forecast"].sum(),
]
forecast = forecast.astype({"q4_25": int, "q4_26_forecast": int})
forecast.to_csv(OUT / "q4_2026_forecast.csv")

model_total = forecast.loc["Total", "q4_26_forecast"]
gap = (model_total / guidance["Q4'26"] - 1) * 100

# Chart
fig, ax = plt.subplots(figsize=(9.5, 4.5))
for r in REGIONS:
    ax.plot(rev.index, rev[r], marker="o", markersize=3, linewidth=2, label=r)
    ax.annotate(f"{r} {rev[r].iloc[-1]:,}", (len(rev) - 1, rev[r].iloc[-1]),
                xytext=(6, {"LATAM": 6, "APAC": -6}.get(r, 0)), textcoords="offset points", va="center", fontsize=9)
ax.set_title("Netflix revenue by region (US$ millions)")
ax.set_ylim(0)
ax.grid(axis="y", alpha=0.3)
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(axis="x", rotation=45)
fig.tight_layout()
fig.savefig(OUT / "revenue_by_region.png", dpi=150)

print(f"Quarters reconciled within ${RECON_TOLERANCE}M: {recon['matches'].sum()} of {len(recon)}")
print(recon.loc[~recon["matches"]], "\n")
print("Unusual quarters:\n", flags.to_string(index=False), "\n")
print("Q4'26 forecast ($M):\n", forecast.to_string(), "\n")
print(f"Model ${model_total:,}M vs guidance ${guidance.iloc[0]:,}M ({gap:+.1f}%)")
