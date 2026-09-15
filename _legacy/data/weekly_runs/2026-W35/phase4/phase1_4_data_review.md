# STORM V2 Phase 1–4 Data & Business Logic Review

Status: `REVIEW_FAILED`

## Source Review

| Source | Status |
| --- | --- |
| Sales Source | PASS |
| Gmv Source | FAIL |
| Cm Source | PASS |
| Market Insight Source | PASS |
| Fixed Cost Source | PASS |
| Return Warranty Source | PASS |
| Funding Source | PASS |
| Thd Dfc Source | PASS |

## Calculation Review

| Calculation | Status |
| --- | --- |
| Sales Contribution | PASS |
| Cm Gap | PASS |
| Tacos | PASS |
| Fixed Cost Rate | PASS |
| Return Warranty Cost Rate | PASS |
| Funding Rate | PASS |
| Known Operating Cost Burden Rate | PASS |

Each derived operating metric retains its formula, exact source values, and source cell references in `operating_efficiency_metrics.csv` and `weekly_business_review.json`.

## Scope Review

| Scope Check | Status |
| --- | --- |
| Hierarchy Mapping | PASS |
| No Forced Lower Level Allocation | PASS |
| Management Summary Not Recast As Detail | PASS |
| Sku Operating Metrics | N/A |

Channel, Brand, and Power Source metrics remain separate source-level views. SKU operating metrics are `N/A`; no allocation was performed.

## Freshness Review

- Common Sales: through **2026-08-17**
- THD DFC: through **2026-08-16**
- CM and Operating Efficiency: **Aug MTD**, exact day-level Data Through **UNKNOWN**

## Business Review

1. **Who sells the most?** THD / DS: $72,258.33.
2. **Who sells the least?** Walmart / MP: $11,795.16.
3. **Where is the Sales gap?** Leader-to-lowest channel gap: $60,463.17 between THD / DS and Walmart / MP.
4. **Who has the best CM?** Walmart / DSV: 29.57%.
5. **Who has the worst CM?** Walmart / MP: -38.85%.
6. **Who has the highest TACOS?** Walmart / MP: 12.48%.
7. **Who depends most on market spend?** Walmart / MP has the highest relative Market Insight burden at 12.48%.
8. **Who has the largest Fixed Cost burden?** Walmart / MP: 57.09%.
9. **Who has the largest Return / Warranty pressure?** Walmart / MP: 15.51%.
10. **Who relies on Funding?** No supported core channel in the current MTD summary. Source-reported Funding is present for  in the parallel Brand/Power Source summaries.
11. **Which channel has strong Sales but weak quality?** No supported channel simultaneously ranks near the top in Sales and below zero CM; Lowe's is commercially strong but has the second-highest Return & Warranty Cost Rate.
12. **Which channel has healthy Sales and CM?** THD / DS leads both Sales and Actual CM and has the second-lowest known operating burden rate.
13. **What is the clearest anomaly?** Walmart / MP: lowest Sales, lowest CM, and the highest TACOS, Fixed Cost Rate, Return & Warranty Cost Rate, and known burden rate.
14. **What is the clearest opportunity?** Walmart / DSV: positive scale, 29.42% Actual CM, zero TACOS/Funding, and the lowest known burden rate; commercial scalability still requires review.

## Review Decision

`REVIEW_FAILED`

Visualization decision: `NO_CHART_ADDED_SMALL_EXACT_CROSS_SECTION_IS_CLEARER_AS_AUDIT_TABLE`. Exact audit tables are more legible than a chart for this four-channel cross-section.
