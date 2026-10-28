# Netflix Regional Revenue Monitor

A small revenue analytics project on Netflix's public numbers. It takes quarterly revenue for Netflix's four regions (Q3'23 to Q3'26), checks that the data adds up, flags quarters that broke from the normal growth pattern, and builds a simple Q4'26 forecast to compare against Netflix's own guidance.

![Revenue by region](outputs/revenue_by_region.png)

## Results

| Check | Result |
| --- | --- |
| Q4'26 forecast (sum of regions) | $13,570M |
| Netflix Q4'26 guidance | $13,442M |
| Model vs guidance | +1.0% |
| Quarters where regions match the reported total (within $1M) | 12 of 13 |

**Forecast by region (US$ millions)**

| Region | Q4'25 actual | Growth used | Q4'26 forecast |
| --- | ---: | ---: | ---: |
| UCAN | 5,339 | 10.6% | 5,904 |
| EMEA | 3,873 | 12.5% | 4,358 |
| LATAM | 1,418 | 19.1% | 1,688 |
| APAC | 1,421 | 14.0% | 1,620 |
| **Total** | **12,051** | **12.6%** | **13,570** |

**Unusual quarters** (quarter-over-quarter growth at least 1.5 standard deviations from that region's average)

| Quarter | Region | QoQ growth | Z-score |
| --- | --- | ---: | ---: |
| Q1'26 | UCAN | -1.8% | -2.02 |
| Q4'24 | LATAM | -0.9% | -1.85 |
| Q2'26 | EMEA | +0.9% | -1.76 |
| Q1'24 | EMEA | +6.2% | 1.74 |
| Q2'26 | APAC | +0.1% | -1.74 |
| Q1'24 | UCAN | +7.5% | 1.51 |

## How it works

1. **Reconciliation.** For each quarter, the four regions are summed and compared with the reported total. The only miss is Q3'23 ($23M), which is most likely the DVD business that shut down that quarter and was reported outside the streaming regions.
2. **Unusual quarters.** Quarter-over-quarter growth is calculated per region and turned into a z-score within that region, so a region is only compared with its own history.
3. **Forecast.** Each region's Q4'25 revenue is grown by the average year-over-year growth of its last two quarters (Q2'26 and Q3'26). Q4'25 is used as the base so seasonality is built in.

The forecast is meant as a simple baseline to sanity-check guidance, not a replacement for it. It ignores currency moves, price changes and the ads business, which Netflix's own forecast accounts for.

## Run it

```bash
pip install -r requirements.txt
python analysis.py
```

The script writes `reconciliation.csv`, `unusual_quarters.csv`, `q4_2026_forecast.csv` and the chart to `outputs/`.

## Data

`data/netflix_revenue_by_region.csv` holds quarterly revenue in US$ millions, entered from Netflix shareholder letters filed with the SEC (Form 8-K, Exhibit 99.1):

- [Q3'24 letter](https://www.sec.gov/Archives/edgar/data/1065280/000106528024000286/ex991_q324.htm) (Q3'23 to Q3'24)
- [Q3'25 letter](https://www.sec.gov/Archives/edgar/data/1065280/000106528025000404/ex991_q325.htm) (Q3'24 to Q3'25)
- [Q2'26 letter](https://www.sec.gov/Archives/edgar/data/0001065280/000106528026000211/ex991_q226.htm) and [Q3'26 letter](https://www.sec.gov/Archives/edgar/data/0001065280/000106528026000290/ex991_q326.htm) (Q2'25 to Q3'26, plus Q4'26 guidance)

## Author

Sai Soumya Aloor · [saialoor@outlook.com](mailto:saialoor@outlook.com)
