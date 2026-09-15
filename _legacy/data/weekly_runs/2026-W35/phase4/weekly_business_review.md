# STORM Weekly Business Review — Phase 4

Snapshot: `2026-08-24_65d8677cc785`  
Source SHA-256: `65D8677CC785CBB81573245EB30ED4A5EA835616D10854149B98953CEDBBD711`  
Status: `STORM_V2_PHASE_4_BLOCKED_BY_REVIEW`

## Executive Summary

THD / DS leads both current approved-core Sales and source-reported Actual CM. Walmart / MP is the clearest operating exception, with the lowest Sales and CM plus the highest relative burden across all four Phase 4 cost measures. Walmart / DSV is the strongest relative opportunity for commercial review because it combines positive scale, strong CM, and the lowest observed operating-support burden.

## Integrated Sales × CM × Cost View

| Channel | Sales | Contribution | Actual CM | CM Gap | GMV | Market Insight | TACOS | Fixed Cost Rate | R&W Cost Rate | Funding Rate | Known Burden Rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| THD / DS | $72,258.33 | 50.8% | 22.01% | 15.22 pp | $87,138.33 | $7,233.39 | 8.30% | 2.75% | 5.58% | 0.00% | 16.63% |
| Lowe's / DS | $39,784.14 | 28.0% | 12.72% | 8.70 pp | $39,556.49 | $1,226.30 | 3.10% | 2.02% | 14.25% | 0.00% | 19.37% |
| Walmart / DSV | $18,398.22 | 12.9% | 29.57% | 23.40 pp | $18,398.22 | $0.00 | 0.00% | 1.00% | 0.00% | 0.00% | 1.00% |
| Walmart / MP | $11,795.16 | 8.3% | -38.85% | -42.96 pp | $11,795.16 | $1,472.46 | 12.48% | 57.09% | 15.51% | 0.00% | 85.08% |

All cost rates use source-reported overview GMV for the same management-summary entity. Common Sales remains a separate approved-core source and is not substituted into cost-rate denominators.

## Source-Reported Operating Costs

| Channel | Market Insight | Fixed Cost | Return + Warranty | Funding | Funding Present | Known Operating Cost Burden |
| --- | --- | --- | --- | --- | --- | --- |
| THD / DS | $7,233.39 | $2,400.64 | $4,859.55 | $0.00 | NO | $14,493.58 |
| Lowe's / DS | $1,226.30 | $799.04 | $5,636.42 | $0.00 | NO | $7,661.76 |
| Walmart / DSV | $0.00 | $183.98 | $0.00 | $0.00 | NO | $183.98 |
| Walmart / MP | $1,472.46 | $6,733.86 | $1,829.03 | $0.00 | NO | $10,035.35 |

The workbook uses positive values to represent costs. Source values are preserved; current rows require no display sign normalization.

## Brand and Power Source Operating View

| Level | Entity | Actual CM | TACOS | Fixed Cost Rate | R&W Cost Rate | Funding Rate | Funding Present | Known Burden Rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BRAND | Badger | 24.52% | 3.77% | 6.79% | 3.81% | 0.00% | NO | 14.38% |
| BRAND | Sunseeker | -8.62% | 17.74% | 16.14% | 7.87% | 0.00% | NO | 41.76% |
| POWER_SOURCE | Gas | 32.94% | 3.52% | 2.81% | 2.49% | 0.00% | NO | 8.82% |
| POWER_SOURCE | Lithium | 1.30% | 5.22% | 18.41% | 7.45% | 0.00% | NO | 31.09% |
| POWER_SOURCE | ACC | 26.73% | 10.08% | 12.37% | 3.52% | 0.00% | NO | 25.97% |
| POWER_SOURCE | Robot | -11.97% | 17.98% | 16.15% | 8.29% | 0.00% | NO | 42.43% |

Brand and Power Source Sales use the approved-core Sales contract, while CM and operating fields use the broader overview management-summary population. They are parallel diagnostic views, not identical-population reconciliations.

## Key Business Findings

1. HEALTHY PERFORMANCE — THD / DS leads Sales at $72,258.33 (50.8%), has the highest Actual CM at 22.01%, and its known operating burden rate is 16.63%.
2. Walmart / MP is the clearest operating anomaly: it has the lowest Sales at $11,795.16, the weakest Actual CM at -38.85%, the highest TACOS at 12.48%, and the highest known burden rate at 85.08%. These are concurrent pressures, not proof that market spend alone caused the CM result.
3. Lowe's / DS has the second-highest Sales at $39,784.14 and Actual CM 12.72%; its Return & Warranty Cost Rate is 14.25%, a notable contributor to current operating pressure relative to the other supported channels.
4. Walmart / DSV combines $18,398.22 of Sales with Actual CM 29.57%, zero TACOS, no Funding, and the lowest known burden rate at 1.00%; it is the clearest relative opportunity for further commercial review.
5. No supported core channel reports Funding in the current MTD management summary.
6. The largest negative CM gap remains Walmart / MP at -42.96 pp; the largest positive gap remains Walmart / DSV at 23.40 pp.

## Data Freshness

- Common Sales — Data Through: **2026-08-17**
- THD DFC Sell-out — Data Through: **2026-08-16**
- CM / Operating Efficiency — Period: **Aug MTD**; Data Through: **UNKNOWN**

## Data Quality and Scope

- `OPERATING_SOURCE_RECONCILIATION_FAILED`: Operating source or derived metric reconciliation did not pass.
- `CM_DAY_LEVEL_FRESHNESS_UNKNOWN`: CM is labeled Aug MTD but has no exact day-level data-through; it is not assumed to equal the Sales data-through date.
- `BRAND_POWER_SCOPE_ALIGNMENT`: Brand and Power Source CM come from the overview US management summaries, while Sales uses the approved core-channel contract; compare these cuts as parallel views, not identical populations.
- `CHANNEL_SALES_OVERVIEW_GMV_DELTA`: THD / DS Common Sales is $72,258.33 versus overview Actual GMV $87,138.33, a $-14,880.00 difference. The retained unmapped Sales row is not used to reconstruct or adjust CM.
- `CHANNEL_SALES_OVERVIEW_GMV_DELTA`: Lowe's / DS Common Sales is $39,784.14 versus overview Actual GMV $39,556.49, a $227.65 difference. The retained unmapped Sales row is not used to reconstruct or adjust CM.
- `OPERATING_DAY_LEVEL_FRESHNESS_UNKNOWN`: Operating costs are labeled Aug MTD; exact day-level data-through is unknown and is not inherited from Sales.
- `THD_MARKET_INSIGHT_INCLUDES_DFC_FIXED_SPEND`: THD / DS overview Market Insight includes the source-reported THD DFC MTD fixed spend of $612.50; the management summary is preserved without reconstruction.
- `KNOWN_OPERATING_COST_BURDEN_SCOPE`: Known Operating Cost Burden includes only Market Insight, Fixed Cost, Return + Warranty, and Funding. It is not CM or complete operating cost.

## Reconciliation

- Phase 2 Common Sales: **PASS**
- Phase 2 THD DFC: **PASS**
- Phase 3 Business Performance: **PASS**
- Phase 4 Operating Source and Derivations: **FAIL**
- Phase 1–4 Data & Business Logic Review: **REVIEW_FAILED**

## Next Steps

Freeze the Phase 1–4 data analysis layer and use these governed fields as the source contract for Phase 5 Dashboard design.

## Further Questions

- Can the exact CM/operating MTD data-through date be added to the workbook control metadata?
- Should the Phase 5 Dashboard show the THD DFC fixed Market Insight scope note directly beside THD TACOS?

## Caveats

- Known Operating Cost Burden is not CM and is not a complete operating-cost total.
- Relative rankings are descriptive; no external or invented performance benchmarks were applied.
- No operating cost was allocated to SKU or another unsupported lower level.
