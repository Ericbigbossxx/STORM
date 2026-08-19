# STORM Weekly Cockpit — Native Feishu Manual Build Specification

Status: `DATA_READY_MANUAL_DASHBOARD_LAYOUT_REQUIRED`

The live Base is dashboard-ready. The current automation surface exposes Base table, field, view, and record APIs, but no dashboard/component CRUD API. Build the native dashboard in the Feishu desktop or web UI using the exact contract below. The machine-readable version is `config/dashboard_metric_contract_v1.yaml`.

## Global configuration

- Dashboard name: `STORM Weekly Cockpit`
- Canvas: approximately 1440px desktop, simple business theme
- Data sources: only `01 Business Health` and `02 Core SKU Performance`
- Global filters: `Control Week` and `Platform`
- Default platform: `Walmart`
- Current control week: `2026-W33`
- Automatic latest-week default: configure only if the native UI supports it directly; otherwise change the selected week manually
- Never display record IDs, field IDs, hashes, batch IDs, or source lineage in the cockpit

## Component order

1. Header / Control Status
2. Sales Performance
3. Profitability
4. Advertising / Inventory
5. Weekly Trend
6. Top Sales Detractors
7. Positive Contributors / Advertising Waste / Availability Attention
8. Data Coverage

## Components

| Component | Type | Source | Field(s) | Aggregation / rule | Filter / sort | Format and placement |
|---|---|---|---|---|---|---|
| Control Status | Text/status | 01 | Platform, Week, Overall Health, Sales Health, CM Health, Data Confidence | No aggregation | Platform=Walmart; selected Week | Full-width header |
| Actual Sales | Metric card | 01 | Actual Sales | Sum | Platform=Walmart; selected Week | USD, row 2 |
| BP Sales | Metric card | 01 | BP Sales | Sum | Same | USD, row 2 |
| Gap to BP | Metric card | 01 | Sales Gap | Sum | Same | USD, row 2 |
| Sales Attainment | Metric card | 01 | Sales Attainment | Average | Same | Percent, 2 decimals, row 2 |
| Actual CM | Metric card | 01 | Actual CM | Sum | Same | USD, row 3 |
| BP CM | Metric card | 01 | BP CM | Sum | Same | USD, row 3 |
| CM Gap | Metric card | 01 | CM Gap | Sum | Same | USD, row 3 |
| CM Attainment | Metric card | 01 | CM Attainment | Average | Same | Percent, 2 decimals, row 3 |
| CM % | Metric card | 01 | CM % | Average | Same | Percent, 2 decimals, row 3 |
| Ad Spend | Metric card | 01 | Ad Spend | Sum | Same | USD, compact row 4 |
| Attributed Sales | Metric card | 01 | Attributed Sales | Sum | Same | USD, compact row 4 |
| ROAS | Metric card | 01 | ROAS | Average | Same | Ratio, 2 decimals, compact row 4 |
| Available Units | Metric card | 01 | Available Units | Sum | Same | Integer, compact row 4 |
| OOS SKU Count | Metric card | 01 | OOS SKU Count | Sum | Same | Integer, compact row 4 |
| Weekly Operating Sales | Line chart | 01 | X=Week; Y=Weekly Operating Sales | Sum | Platform=Walmart; Week ascending | USD, 8 columns, row 5 |
| Weekly Change Context | Two metric cards | 01 | Weekly Sales Change $, Weekly Sales Change % | Sum; Average | Platform=Walmart; selected Week | USD and percent, 4 columns, row 5 |
| Top Sales Detractors | Ranking/table | 02 | SKU, SKU Role, Sales, Target, Sales Gap, Sales Attainment, Evidence | Row values | Platform=Walmart; selected Week; Sales Gap not blank; sort Sales Gap ascending; Top 5 | Full width, row 6 |
| Positive Contributors | Ranking/table | 02 | SKU, SKU Role, Sales Gap | Row values | Sales Gap > 0; descending; Top 3 | 4 columns, row 7 |
| Advertising Waste | Ranking/table | 02 | SKU, Ad Spend, Attributed Sales, ROAS | Row values | Ad Spend > 0 AND Attributed Sales = 0; spend descending; Top 3 | 4 columns, row 7 |
| Availability Attention | Ranking/table | 02 | SKU, SKU Role, Inventory, Target, Evidence | Row values | Inventory = 0 AND Target > 0; Target descending; Top 3 | 4 columns, row 7 |
| Data Coverage | Date cards | 01 | Sales Data Through, CM Data Through, Ads Data Through, Inventory Data Through | Max | Platform=Walmart; selected Week | `yyyy-MM-dd`, full width, visually secondary |

## Current live-state notes

- `01 Business Health` contains one weekly record, so the trend chart currently has one point. Do not fabricate history. Future weekly records will extend it when the component is bound to `Week`.
- Display `YTD: SOURCE_NOT_AVAILABLE` as a static secondary annotation. No fake YTD value or status field was created.
- Current live Top 5 detractor order is `SKRMX3PLUS`, `WB20V16LM`, `WB40V18PLM`, `SKRMV3`, `WB40VTBCC`.
- Current live focused attention sets are:
  - Positive: `WB40VTRED`
  - Advertising waste: `WB40V18PLM`, `WB20VTRSBL`, `WB40VTBCC`
  - Availability: `WB53CULT`, `WB26MTSE`, `WBPMT26P`

