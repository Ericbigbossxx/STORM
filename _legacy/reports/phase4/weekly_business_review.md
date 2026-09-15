# STORM Weekly Business Review — Phase 4

Snapshot: `2026-08-13_b05ff566b9de`  
Source SHA-256: `B05FF566B9DECC2852460E8FEC12AF8026B0C8D72148F52F974C32F27F1A8833`  
Status: `STORM_V2_PHASE_4_OPERATING_INSIGHT_COMPLETE`

## Executive Summary

THD / DS leads both current approved-core Sales and source-reported Actual CM. Walmart / MP is the clearest operating exception, with the lowest Sales and CM plus the highest relative burden across all four Phase 4 cost measures. Walmart / DSV is the strongest relative opportunity for commercial review because it combines positive scale, strong CM, and the lowest observed operating-support burden.

## Integrated Sales × CM × Cost View

| Channel | Sales | Contribution | Actual CM | CM Gap | GMV | Market Insight | TACOS | Fixed Cost Rate | R&W Cost Rate | Funding Rate | Known Burden Rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| THD / DS | $38,617.77 | 45.9% | 37.53% | 30.74 pp | $38,617.77 | $1,535.54 | 3.98% | 2.20% | 1.15% | 0.00% | 7.32% |
| Lowe's / DS | $23,510.54 | 28.0% | 14.82% | 10.79 pp | $23,376.48 | $1,067.78 | 4.57% | 2.02% | 11.54% | 0.00% | 18.13% |
| Walmart / DSV | $16,211.64 | 19.3% | 29.42% | 23.25 pp | $16,211.64 | $0.00 | 0.00% | 1.00% | 0.00% | 0.00% | 1.00% |
| Walmart / MP | $5,750.92 | 6.8% | -56.92% | -61.03 pp | $5,750.92 | $1,081.19 | 18.80% | 64.23% | 20.38% | 0.00% | 103.41% |

All cost rates use source-reported overview GMV for the same management-summary entity. Common Sales remains a separate approved-core source and is not substituted into cost-rate denominators.

## Source-Reported Operating Costs

| Channel | Market Insight | Fixed Cost | Return + Warranty | Funding | Funding Present | Known Operating Cost Burden |
| --- | --- | --- | --- | --- | --- | --- |
| THD / DS | $1,535.54 | $849.59 | $443.07 | $0.00 | NO | $2,828.20 |
| Lowe's / DS | $1,067.78 | $472.20 | $2,697.03 | $0.00 | NO | $4,237.01 |
| Walmart / DSV | $0.00 | $162.12 | $0.00 | $0.00 | NO | $162.12 |
| Walmart / MP | $1,081.19 | $3,693.64 | $1,172.00 | $0.00 | NO | $5,946.83 |

The workbook uses positive values to represent costs. Source values are preserved; current rows require no display sign normalization.

## Brand and Power Source Operating View

| Level | Entity | Actual CM | TACOS | Fixed Cost Rate | R&W Cost Rate | Funding Rate | Funding Present | Known Burden Rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BRAND | Badger | 2.45% | 8.08% | 27.44% | 0.68% | 0.25% | YES | 36.45% |
| BRAND | Sunseeker | -7.15% | 20.11% | 17.84% | 2.99% | 0.00% | NO | 40.93% |
| POWER_SOURCE | Gas | 8.16% | 7.07% | 23.79% | 0.36% | 0.23% | YES | 31.44% |
| POWER_SOURCE | Lithium | -8.13% | 9.77% | 33.24% | 1.06% | 0.29% | YES | 44.37% |
| POWER_SOURCE | ACC | 15.92% | 10.58% | 22.73% | 0.85% | 0.16% | YES | 34.32% |
| POWER_SOURCE | Robot | -10.01% | 20.50% | 18.03% | 3.28% | 0.00% | NO | 41.82% |

Brand and Power Source Sales use the approved-core Sales contract, while CM and operating fields use the broader overview management-summary population. They are parallel diagnostic views, not identical-population reconciliations.

## Key Business Findings

1. HEALTHY PERFORMANCE — THD / DS leads Sales at $38,617.77 (45.9%), has the highest Actual CM at 37.53%, and its known operating burden rate is 7.32%.
2. Walmart / MP is the clearest operating anomaly: it has the lowest Sales at $5,750.92, the weakest Actual CM at -56.92%, the highest TACOS at 18.80%, and the highest known burden rate at 103.41%. These are concurrent pressures, not proof that market spend alone caused the CM result.
3. Lowe's / DS has the second-highest Sales at $23,510.54 and Actual CM 14.82%; its Return & Warranty Cost Rate is 11.54%, a notable contributor to current operating pressure relative to the other supported channels.
4. Walmart / DSV combines $16,211.64 of Sales with Actual CM 29.42%, zero TACOS, no Funding, and the lowest known burden rate at 1.00%; it is the clearest relative opportunity for further commercial review.
5. No supported core channel reports Funding in the current MTD management summary.
6. The largest negative CM gap remains Walmart / MP at -61.03 pp; the largest positive gap remains THD / DS at 30.74 pp.

## Data Freshness

- Common Sales — Data Through: **2026-08-10**
- THD DFC Sell-out — Data Through: **2026-08-10**
- CM / Operating Efficiency — Period: **Aug MTD**; Data Through: **UNKNOWN**

## Data Quality and Scope

- `CM_DAY_LEVEL_FRESHNESS_UNKNOWN`: CM is labeled Aug MTD but has no exact day-level data-through; it is not assumed to equal the Sales data-through date.
- `BRAND_POWER_SCOPE_ALIGNMENT`: Brand and Power Source CM come from the overview US management summaries, while Sales uses the approved core-channel contract; compare these cuts as parallel views, not identical populations.
- `CHANNEL_SALES_OVERVIEW_GMV_DELTA`: Lowe's / DS Common Sales is $23,510.54 versus overview Actual GMV $23,376.48, a $134.06 difference. The retained unmapped Sales row is not used to reconstruct or adjust CM.
- `OPERATING_DAY_LEVEL_FRESHNESS_UNKNOWN`: Operating costs are labeled Aug MTD; exact day-level data-through is unknown and is not inherited from Sales.
- `THD_MARKET_INSIGHT_INCLUDES_DFC_FIXED_SPEND`: THD / DS overview Market Insight includes the source-reported THD DFC MTD fixed spend of $612.50; the management summary is preserved without reconstruction.
- `KNOWN_OPERATING_COST_BURDEN_SCOPE`: Known Operating Cost Burden includes only Market Insight, Fixed Cost, Return + Warranty, and Funding. It is not CM or complete operating cost.

## Reconciliation

- Phase 2 Common Sales: **PASS**
- Phase 2 THD DFC: **PASS**
- Phase 3 Business Performance: **PASS**
- Phase 4 Operating Source and Derivations: **PASS**
- Phase 1–4 Data & Business Logic Review: **DATA_ANALYSIS_LAYER_COMPLETE**

## Next Steps

Freeze the Phase 1–4 data analysis layer and use these governed fields as the source contract for Phase 5 Dashboard design.

## Further Questions

- Can the exact CM/operating MTD data-through date be added to the workbook control metadata?
- Should the Phase 5 Dashboard show the THD DFC fixed Market Insight scope note directly beside THD TACOS?

## Caveats

- Known Operating Cost Burden is not CM and is not a complete operating-cost total.
- Relative rankings are descriptive; no external or invented performance benchmarks were applied.
- No operating cost was allocated to SKU or another unsupported lower level.
