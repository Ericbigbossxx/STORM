# STORM Structured Metrics Input — Architecture & Build Specification v1

**Status:** Architecture frozen for V1 build  
**Scope:** Walmart MP, THD, Lowe's  
**Excluded from structured metrics:** Walmart Owner (control/issue tracking only until operational control is restored)  
**Primary purpose:** Weekly Business Control cockpit, not a full operating system and not a replacement for existing finance/CM workbook.

---

## 0. Codex execution mandate

Build the first production-ready version of **STORM Structured Metrics Input** from this specification.

Before implementation:
1. Inspect the existing STORM project structure in read-only mode.
2. Inspect the current CM workbook structure and any existing STORM/Feishu tables without modifying source data.
3. Produce a short implementation map showing how the existing assets map to the V1 schema below.
4. Then implement in the smallest sufficient way. Do not introduce a broad data warehouse, a new finance engine, or a full analytics platform.

Non-negotiable engineering rules:
- Preserve source files; never rewrite the official CM workbook.
- Keep historical imports immutable; a new weekly import creates a new snapshot/batch instead of overwriting history.
- Be idempotent: re-importing the same source/report period must not duplicate facts.
- Unknown/unmapped data must be surfaced as a data exception, not silently dropped or coerced to zero.
- `N/A` is not `0`.
- Do not unify platform metrics merely for visual symmetry.
- Prefer explicit business semantics over generic metric names.
- Do not build Streamlit or an advanced dashboard in this phase unless the existing STORM project already requires it. The priority is a reliable Structured Metrics Input layer and the views needed for the weekly control process.

---

# 1. Business purpose

STORM must help answer four questions every week:

1. **MTD:** Where is the business this month versus BP?
2. **YTD:** Where is the business for the year versus BP?
3. **Change:** Has the business position improved or deteriorated since the previous weekly maintenance snapshot?
4. **Driver:** Which Platform → Brand × Power Source → SKU / CM driver / inventory / ads / refund issue explains the change?

STORM is a **business control cockpit**. It should surface the few metrics and exceptions that drive a decision. It is not intended to reproduce every report, keyword, campaign, order, inventory detail, or finance calculation.

---

# 2. Fixed management hierarchy

The reporting hierarchy is fixed as follows.

## Level 1 — Platform

- THD
- Lowe's
- Walmart MP

Primary question: **Which channel is ahead/behind plan and where is the main risk?**

## Level 2 — Brand × Power Source

This is a **fixed operating view**, not merely a filter.

Examples from the current CM model include brand/power-source combinations such as:
- Sunseeker × Robot
- Sunseeker × ACC
- Badger × Lithium
- Badger × Gas

Do not hard-code the examples. Source the valid values from the SKU master.

Primary question: **Which business block is driving the platform result?**

## Level 3 — SKU Exception

SKU is not a permanently expanded giant table. It is an exception/drill-down layer.

The SKU view must support filters for:
- Platform
- Brand
- Power Source
- SKU

Primary question: **Which specific SKU(s) explain the gap or require action?**

SKU exception ranking should prefer contribution to business gap rather than simply ranking percentage changes.

---

# 3. Canonical platform definitions

## 3.1 THD

**Business model:** 1P  
**Primary Sales basis:** Sell-in  
**Primary Sales value:** Vendor Revenue / Cost basis (revenue earned from THD purchase orders)  
**DFC Sell-out:** Separate sell-through / inventory-health signal only for eligible SKUs. It must NOT be added to THD Primary Sales.

THD therefore has two separate analytical tracks:

### THD Primary Business
- Sell-in Vendor Revenue
- Sell-in Units
- BP / attainment
- official management CM for the THD 1P sell-in business

### THD DFC Health
- DFC Sell-out
- DFC inventory
- WOS
- related sell-through/inventory signals

**Critical rule:** Do not recreate the current CM Overview behavior that adds `THD Main + THD DFC` and calls it one THD sales total. For STORM, THD primary sales is sell-in only.

## 3.2 Lowe's

**Business model:** 1P  
**Primary Sales basis:** Sell-in  
**Primary Sales value:** Vendor Revenue / Cost basis  
**Primary order source:** same shared order report used by THD, split by platform/channel.

No inventory module is required in V1 unless a new operating need is confirmed later.

## 3.3 Walmart MP

**Business model:** Marketplace  
**Primary Sales basis:** Sell-out / consumer sales  
**WFS:** Fulfillment/warehouse layer only. WFS does not create a separate sales basis.

Walmart MP operating health includes:
- sell-out sales
- WFS inventory / WOS
- WFS storage fee
- refunds
- ads

## 3.4 Walmart Owner

Do not place Walmart Owner into Structured Metrics V1.

Current status is a control problem, not a metric problem. Track it in STORM Control Ledger / Issue-Risk area, e.g.:
- Portal Access
- Item Control
- Inventory Control
- PO / Order Visibility
- Merchant Contact
- DSV Connectivity

Only promote Owner into Structured Metrics after the account/business becomes operationally controllable.

---

# 4. Sales semantics and cross-platform reporting

Use a common management label such as **Primary Sales** or **Management Sales**, while always retaining the actual sales basis as metadata.

Canonical values:
- THD → `SELL_IN_VENDOR_REVENUE`
- LOWES → `SELL_IN_VENDOR_REVENUE`
- WALMART_MP → `SELL_OUT_CONSUMER_REVENUE`

Never label the cross-platform aggregate as consumer GMV.

A cross-platform total may be shown only as something equivalent to:

**Total Sales — Management Basis**

with a visible or readily accessible note:

`1P = Sell-in | MP = Sell-out`

This total is valid for internal BP/management control because the BP uses each channel's management basis. It is not a statement of total end-consumer sales.

---

# 5. Core weekly metrics

## 5.1 Cross-platform common metrics

### Sales / Scale
At Platform and Brand × Power Source level:
- `mtd_actual_sales`
- `mtd_bp_sales`
- `mtd_bp_completion = mtd_actual_sales / mtd_bp_sales`
- `mtd_bp_completion_delta_vs_prev_snapshot` (percentage points)
- `mtd_actual_delta_vs_prev_snapshot`
- `ytd_actual_sales`
- `ytd_bp_sales`
- `ytd_bp_attainment = ytd_actual_sales / ytd_bp_sales`
- `ytd_bp_attainment_delta_vs_prev_snapshot` (percentage points)
- `sales_units` retained in the data model; not necessarily displayed on the fixed Level 2 view

### Profitability / Contribution
CM is a first-class weekly metric.

At Platform and Brand × Power Source level:
- `mtd_actual_cm`
- `mtd_actual_cm_pct`
- `mtd_bp_cm`
- `mtd_bp_cm_pct`
- `mtd_cm_variance = actual_cm - bp_cm`
- `mtd_cm_margin_variance_ppt = actual_cm_pct - bp_cm_pct`
- YTD equivalents where supported by the official CM workbook

Do NOT use `Actual CM / BP CM` as the primary management KPI. It is unstable and misleading when BP CM is near zero or negative.

CM comparisons should emphasize:
- absolute CM variance ($)
- CM margin variance (percentage points)

## 5.2 Optional pacing signal

For MTD sales, calculate a lightweight calendar pacing signal:
- `month_progress_pct = elapsed_calendar_days / days_in_month`
- `sales_pace_gap_ppt = mtd_bp_completion - month_progress_pct`

This is a **pacing signal, not a forecast**, especially for 1P PO-based businesses where orders are lumpy.

Do not treat a negative pace gap as proof of month-end failure.

---

# 6. Platform-specific metrics

## 6.1 THD

### Primary business
Use common Sales + CM metrics above.

### DFC health (eligible SKUs only)
Minimum:
- DFC Sell-out sales or units (report-native measure; retain both if available)
- current DFC on-hand inventory
- WOS
- previous snapshot WOS
- WOS change
- inventory change

If sell-in and sell-out are compared for the same SKU population, only use SKUs marked `dfc_sellout_eligible = true`.

Never compare total THD sell-in universe with partial DFC sell-out universe and interpret it as a channel conversion rate.

### Ads
V1 core:
- Spend
- Attributed Sales
- Orders
- ROAS
- MTD values and change versus previous comparable snapshot

CTR/CPC/keyword/search-term/placement belong to diagnosis, not the core cockpit, unless later promoted by a confirmed business need.

Do not calculate THD TACOS using THD sell-in sales as the denominator.

## 6.2 Lowe's

### Primary business
Use common Sales + CM metrics.

### Ads
V1 core:
- Spend
- Attributed Sales
- Orders
- ROAS
- MTD values and change versus previous comparable snapshot

Current weekly minimum source should prefer Campaign Summary.

Keep Activity and Missed Opportunities as diagnostic reports; do not require them for every STORM weekly refresh unless the core metrics trigger an issue.

Do not calculate Lowe's TACOS against Lowe's sell-in vendor revenue.

## 6.3 Walmart MP

### Primary business
Use common Sales + CM metrics.

### WFS inventory
Minimum:
- available/on-hand inventory
- WOS
- WOS change vs prior snapshot
- aged inventory if reliably available
- inventory change vs prior snapshot

### WFS storage fee
Track the fee using the report's real period semantics.

If source provides MTD, label as MTD.
If source provides rolling 30-day values, store and display as `R30`, not MTD.
Never relabel a rolling period as a calendar period.

### Refunds
Minimum:
- refund amount
- refund units/count if reliably available
- refund rate
- change vs previous comparable snapshot
- top refund reason only when useful for exception explanation

### Ads
Minimum:
- Spend
- Attributed Sales
- Orders
- ROAS
- TACOS

TACOS is valid for Walmart MP because both ad spend and primary sales are on the consumer sell-out business, but the numerator and denominator must be aligned to the same effective cutoff date.

---

# 7. CM workbook role and source-of-truth rules

The existing workbook `US E-commerce Actual CM for 2026_vs. BP.xlsx` is treated as the **Official Management CM Model** for V1.

STORM must NOT recreate the complete finance allocation engine.

## 7.1 What STORM should read from the CM workbook

Use the workbook for:
- official BP target data
- official management GM/CM/CM% snapshot
- Brand and Power Source reference/mapping seed
- CM driver information when reliable and useful for explanations

Likely source areas identified in the current workbook:
- `KPI Rawdata` → detailed BP source
- `SKU Mapping` → starting SKU/Brand/Power Source mapping
- `Actual Orders` → useful sales fact/reference source
- `2026 Actual Cost` / platform profitability sheets → CM model inputs/validation
- `Overview` → official management output/reference, but not blindly reusable for THD combined sales

## 7.2 What STORM must not do

- Do not replace the official CM workbook in V1.
- Do not recalculate the full CM model independently and create a competing official number.
- Do not treat revenue-allocated SKU costs as proof of direct SKU-level expense attribution.
- Do not copy the current THD `Main + DFC` combined sales logic into Primary Sales.

## 7.3 CM hierarchy semantics

- Platform CM → official management CM
- Brand × Power Source CM → management allocated CM, valid for operating control
- SKU CM → indicative/allocated signal only unless directly attributable costs exist

At SKU exception level, explain problems using direct operational facts where possible: sales, ads, refunds, inventory, WOS, sell-through.

## 7.4 Quarter/Half-year warning

Do not trust existing workbook Q1/Q2/Q3/Q4/H1/H2 aggregate formulas without independent reconciliation. Prior inspection found formula-shift behavior in some sections.

If STORM needs quarter or half-year metrics, derive them from normalized monthly facts/targets.

MTD and YTD remain the V1 weekly focus.

---

# 8. Time model — mandatory architecture

This is one of the most important parts of V1.

Different reports naturally have different latency. Example weekly refresh may look like:
- THD Sell-in through Aug 11
- THD DFC Sell-out through Aug 8
- Walmart Sales through Aug 10
- Walmart Ads through Aug 9
- WFS inventory snapshot Aug 11

Do not force all reports to truncate to the oldest date just for visual symmetry.

## 8.1 Required time fields

Every imported dataset/metric must distinguish:

### `snapshot_date`
The STORM maintenance/import date, usually Tuesday before Wednesday weekly meeting.

### `data_through_date`
The latest business date actually represented in the source metric/report.

### `period_type`
Examples:
- MTD
- YTD
- DAILY
- SNAPSHOT
- R30
- MONTH

Also retain `period_start_date` / `period_end_date` when report-native and useful.

## 8.2 Weekly change is not naive WoW

Do not define the core weekly comparison as “this import vs last import = WoW sales growth”.

For MTD/YTD management metrics:
- current MTD snapshot is compared with the previous snapshot for the **same month**
- current YTD snapshot is compared with the previous YTD snapshot
- label the result as `delta_vs_prev_snapshot`, not weekly growth

Examples:
- MTD BP Completion: 21.5% → 38.0% = `+16.5 ppt vs previous snapshot`
- MTD Actual: $215K → $380K = `+$165K since previous snapshot`

At a month boundary, do not compare the new month's first MTD snapshot against the previous month's MTD as if they were comparable. Reset MTD comparison by `year_month`.

## 8.3 Snapshot metrics

Inventory/WOS use:
- current snapshot
- previous snapshot
- change between snapshots

They are point-in-time health metrics, not MTD flow metrics.

## 8.4 Cross-source alignment rule

A metric that combines multiple source systems must use a common effective cutoff.

`aligned_through_date = min(component data_through_dates)`

Examples:
- Walmart TACOS: sales through Aug 10 + ads through Aug 9 → TACOS must use sales and ads through Aug 9.
- Any THD sell-in/sell-out relational analysis must align the compared period and matched SKU universe.
- Refund rate using a separate refund source and sales denominator must be aligned if the source does not already provide a valid native rate.

Single-source metrics such as ad-report ROAS can use the report's own `data_through_date`.

## 8.5 CM time semantics

If the official CM workbook does not expose reliable component-level cutoff dates, record CM as:
- `snapshot_date`
- `period_type = MTD / YTD`
- `source = OFFICIAL_CM_WORKBOOK`
- optional component freshness metadata when available

Do not invent a false precise CM `data_through_date`.

---

# 9. Proposed STORM tables

Keep the schema small and domain-specific.

## 9.1 `DIM_SKU`

Purpose: single source for canonical classification and platform eligibility.

Minimum fields:
- `canonical_sku`
- `platform`
- `platform_sku` / alias if needed
- `brand`
- `power_source`
- `category` / product line if already available
- `business_model` (`1P`, `MP`)
- `primary_sales_basis`
- `fulfillment_type` (`DFC`, `WFS`, `OTHER`, nullable)
- `dfc_sellout_eligible` boolean
- `inventory_metric_eligible` boolean
- `active` boolean
- `effective_from`
- `effective_to` optional
- mapping/source note

Seed from the current `SKU Mapping` sheet, then extend with platform-specific attributes.

## 9.2 `FACT_BP_TARGET_MONTHLY`

Grain: `year_month × platform × canonical_sku`

Minimum fields:
- year
- month
- platform
- canonical_sku
- bp_units
- bp_sales
- bp_cm
- bp_cm_pct if directly available/reliably derived
- source_file / source_sheet
- import_batch_id

Brand and Power Source should be joined from `DIM_SKU`, not repeatedly manually maintained.

Primary source: `KPI Rawdata` in the CM workbook.

## 9.3 `FACT_SALES_DAILY`

Preferred grain: `business_date × platform × canonical_sku × sales_basis`

Store daily SKU aggregates rather than unnecessary order-line detail unless the existing importer already supports order detail cleanly.

Minimum fields:
- business_date
- platform
- canonical_sku
- sales_basis
- sales_amount
- units
- source_report
- data_through_date
- import_batch_id

Sources:
- shared THD/Lowe's Order report
- Walmart MP sales fact / reusable output from the existing Walmart operation system

## 9.4 `FACT_CM_SNAPSHOT`

Grain: `snapshot_date × period_type × platform × brand × power_source`

Minimum fields:
- snapshot_date
- period_type (`MTD`, `YTD`)
- platform
- brand
- power_source
- primary_sales_basis
- actual_sales
- actual_units if reliable
- actual_gm
- actual_gm_pct
- actual_cm
- actual_cm_pct
- bp_sales
- bp_units if available
- bp_cm
- bp_cm_pct
- sales_bp_completion
- cm_variance
- cm_margin_variance_ppt
- cm_basis (`OFFICIAL_MANAGEMENT` / `MANAGEMENT_ALLOCATED`)
- source_file
- import_batch_id

For THD, this table must represent THD **Main sell-in business** for primary CM. Do not include DFC sell-out in THD Primary Sales/Primary CM.

## 9.5 `FACT_SELLTHROUGH_DAILY`

Scope: THD DFC only.

Preferred grain: `business_date × platform × canonical_sku`

Minimum fields:
- business_date
- platform (`THD`)
- canonical_sku
- sellout_sales if available
- sellout_units
- data_through_date
- source_report
- import_batch_id

Reject or flag records for SKUs not eligible for DFC sell-through analysis.

## 9.6 `FACT_INVENTORY_SNAPSHOT`

Grain: `snapshot_date × platform × canonical_sku × inventory_network`

Minimum fields:
- snapshot_date
- data_through_date
- platform
- canonical_sku
- inventory_network (`THD_DFC`, `WALMART_WFS`)
- on_hand / available_inventory
- wos
- aged_inventory if available
- source_report
- import_batch_id

Do not calculate WOS from mismatched data if the platform/report already provides an official/reliable WOS.

## 9.7 `FACT_ADS_SNAPSHOT`

Do not force every platform to the same native report grain.

Minimum normalized fields:
- snapshot_date
- period_type (`MTD` preferred for weekly management view)
- period_start_date
- data_through_date
- platform
- canonical_sku nullable
- campaign_id/name nullable
- spend
- attributed_sales
- orders
- roas
- clicks optional
- source_report
- import_batch_id

The cockpit may aggregate this to Platform or Brand × Power Source only when mapping is reliable.

## 9.8 `FACT_REFUND`

Scope: Walmart MP V1.

Use the most reliable source grain available; normalize enough to calculate/report:
- snapshot/period date fields
- canonical_sku where available
- refund_amount
- refund_units/count
- refund_reason where available
- refund_rate (native or aligned-derived)
- source_report
- import_batch_id

## 9.9 `FACT_OPERATING_FEE_SNAPSHOT`

Scope initially includes Walmart WFS storage fee.

Minimum fields:
- snapshot_date
- period_type (`MTD`, `R30`, etc.)
- period_start_date
- data_through_date
- platform
- canonical_sku nullable
- fee_type (`WFS_STORAGE`)
- fee_amount
- source_report
- import_batch_id

Do not mix a flow fee into an inventory point-in-time table without an explicit period semantic.

## 9.10 `IMPORT_BATCH`

Every ingest creates/uses a batch record.

Minimum fields:
- import_batch_id
- snapshot_date
- source_system/platform
- source_report_type
- source_filename
- file_hash
- imported_at
- period_start_date
- data_through_date
- row_count_in
- row_count_loaded
- row_count_rejected
- status
- notes

## 9.11 `DATA_EXCEPTION`

Minimum fields:
- exception_id
- import_batch_id
- exception_type
- platform
- raw_sku / key
- description
- severity
- status
- first_seen
- last_seen
- resolved_at

Initial exception types should include:
- UNMAPPED_SKU
- DUPLICATE_IMPORT
- MISSING_REQUIRED_FIELD
- INVALID_DATE
- INVALID_SALES_BASIS
- NON_ELIGIBLE_DFC_SKU
- DATA_FRESHNESS_ANOMALY
- CM_RECONCILIATION_MISMATCH

Do not silently classify unmapped SKUs as `Other`.

---

# 10. Derived management view / metric layer

Do not require users to manually maintain derived weekly values.

The system should derive a normalized weekly management output (table or view) with at least:

- snapshot_date
- platform
- brand
- power_source
- sales_basis
- MTD Actual Sales
- MTD BP
- MTD BP Completion
- MTD BP Completion Δ vs previous same-month snapshot
- YTD Actual Sales
- YTD BP
- YTD BP Attainment
- YTD BP Attainment Δ vs previous snapshot
- MTD CM
- MTD CM%
- MTD CM variance
- MTD CM margin variance ppt
- YTD CM / CM% / variance where official data supports it
- data freshness summary
- primary signal/status placeholders

Threshold-based red/yellow/green logic must be configurable. Do not invent one universal threshold across platforms in V1.

Until thresholds are confirmed, surface:
- largest negative Sales BP gaps
- largest negative CM gaps
- largest deterioration vs previous snapshot
- largest inventory/WOS exceptions
- largest ads efficiency deterioration
- Walmart refund exceptions

---

# 11. Minimum source report matrix

## 11.1 Common / finance

### Official CM Workbook
**Frequency:** weekly snapshot after the CM workbook is refreshed  
**Purpose:** official CM/GM/BP management snapshot and target/reference data  
**Automation value:** high for extraction; do not automate/rebuild the workbook's finance logic in V1.

### KPI Rawdata within CM workbook
**Frequency:** only when BP changes / initial load  
**Purpose:** monthly SKU-level BP target normalization  
**Automation value:** high for parser; low need for weekly re-import if unchanged.

## 11.2 THD + Lowe's

### Shared Order Report
**Required:** yes  
**Frequency:** weekly  
**Grain:** preserve date + SKU, aggregate to daily SKU facts  
**Minimum raw fields:**
- order/business date
- channel/platform/customer identifier
- SKU
- ordered units
- ordered value / vendor revenue
- order identifier optional for dedupe if needed

**Destination:** `FACT_SALES_DAILY`

## 11.3 THD

### DFC Sell-out Report
**Required:** yes for DFC-eligible robot SKUs  
**Frequency:** weekly  
**Minimum fields:**
- business date / period
- SKU/item
- sell-out units
- sell-out sales if available
- report cutoff date

**Destination:** `FACT_SELLTHROUGH_DAILY`

### DFC Inventory / WOS Report
**Required:** yes  
**Frequency:** weekly snapshot  
**Minimum fields:**
- SKU/item
- on-hand / available inventory
- WOS
- snapshot/report cutoff date
- aged/health field only if reliably available and useful

**Destination:** `FACT_INVENTORY_SNAPSHOT`

### THD Ads Campaign Performance
**Required for V1 ads:** yes  
**Frequency:** weekly MTD refresh  
**Minimum fields:**
- campaign identifier/name
- spend
- attributed sales
- orders
- ROAS or enough fields to calculate it
- period start
- report cutoff date

**Destination:** `FACT_ADS_SNAPSHOT`

Product/keyword/search-term reports remain diagnostic or Phase 2 unless needed for reliable SKU/segment attribution.

## 11.4 Lowe's

### Lowe's Campaign Summary
**Required for V1 ads:** yes  
**Frequency:** weekly MTD refresh  
**Minimum fields:**
- campaign identifier/name
- spend
- attributed sales
- orders/conversions
- ROAS or enough fields to calculate it
- period start
- report cutoff date

**Destination:** `FACT_ADS_SNAPSHOT`

Activity Report and Missed Opportunities remain diagnostic; not mandatory weekly Structured Metrics inputs.

## 11.5 Walmart MP

Prefer reusing normalized outputs/facts from the existing Walmart operation system rather than creating duplicate exports and pipelines.

### Walmart Sales
**Required:** yes  
**Frequency:** weekly refresh / reuse latest fact  
**Minimum fields:** date, SKU, sales, units, cutoff  
**Destination:** `FACT_SALES_DAILY`

### WFS Inventory Health
**Required:** yes  
**Frequency:** weekly snapshot  
**Minimum fields:** SKU, available/on-hand, WOS, aged inventory if useful, cutoff  
**Destination:** `FACT_INVENTORY_SNAPSHOT`

### WFS Storage Fee
**Required:** yes  
**Frequency:** weekly  
**Minimum fields:** SKU where available, fee, true source period, cutoff  
**Destination:** `FACT_OPERATING_FEE_SNAPSHOT`

### Walmart Refund Report
**Required:** yes  
**Frequency:** weekly MTD/YTD as supported  
**Minimum fields:** SKU, refund amount, refund count/units, reason if available, transaction/period date, cutoff  
**Destination:** `FACT_REFUND`

### Walmart Ads
**Required:** yes  
**Frequency:** weekly MTD refresh  
**Minimum fields:** campaign/SKU where available, spend, attributed sales, orders, ROAS, period/cutoff  
**Destination:** `FACT_ADS_SNAPSHOT`

For TACOS, join only through an aligned cutoff date.

---

# 12. Field normalization rules

For every importer:
1. Retain the source filename and report type.
2. Normalize platform names to canonical enum values.
3. Normalize SKU through the platform alias → canonical SKU mapping.
4. Enrich Brand and Power Source from `DIM_SKU`; do not trust report-specific naming if a canonical mapping exists.
5. Preserve source period and cutoff semantics.
6. Validate required numeric fields.
7. Reconcile input/output row counts and sums.
8. Send unmapped/rejected records to `DATA_EXCEPTION`.

Never hard-code Brand or Power Source by substring rules when the SKU master can supply the value.

---

# 13. Data freshness behavior

The cockpit should surface freshness without clutter.

Example:
- Sales: through 8/10
- Ads: through 8/9
- WFS: 8/11 snapshot

Normal platform latency should not automatically create an issue.

Create a `DATA_FRESHNESS_ANOMALY` only when the source is materially older than its expected normal latency. Expected latency should be configured by report type, not globally.

---

# 14. SKU exception logic

V1 should generate an exception candidate list rather than expose every SKU all the time.

Candidate reasons:
- largest negative MTD Sales BP gap contribution
- largest negative CM variance contribution
- CM% deterioration / gap vs BP
- WOS materially high or low
- inventory growing while DFC sell-through is weak (matched eligible THD SKUs only)
- ad spend increasing while ROAS deteriorates
- high-spend / low-return ad item
- Walmart refund rate or refund value exception
- unmapped/data-quality issues

Do not hard-code business thresholds until confirmed. Implement rank-based detection and a configurable rule table/placeholders first.

---

# 15. Dashboard/view contract for V1

## View A — Platform Executive Control

For each of THD / Lowe's / Walmart MP show compactly:
- MTD Primary Sales
- MTD BP Completion
- change vs previous snapshot
- YTD Sales / YTD BP Attainment
- MTD CM
- MTD CM%
- CM variance / CM margin variance
- most important platform-specific signal
- freshness note

Do not show dozens of operational metrics.

## View B — Brand × Power Source Fixed Operating View

Recommended default columns:
- Brand × Power Source
- MTD Sales
- MTD BP Completion
- change vs previous snapshot
- MTD CM
- MTD CM%
- CM margin variance vs BP
- primary signal / exception count

Do not make Units a default column unless it materially improves the current business review; keep it available in drill-down.

## View C — SKU Exception Board

Filters:
- Platform
- Brand
- Power Source
- SKU

Display only selected/exception SKUs with the direct metrics needed to explain the issue.

Platform-specific drill-down fields may differ.

---

# 16. Manual vs automation boundary

## Manual / low-frequency maintenance
- SKU master corrections and new SKU onboarding
- BP updates when annual/monthly BP changes
- business threshold/rule configuration
- Walmart Owner control status until the business becomes controllable

## Automate early (high ROI)
- CM workbook extraction into structured CM snapshots
- KPI Rawdata → monthly BP normalization
- THD/Lowe's shared Order report parsing and platform split
- reuse/import from the existing Walmart operation system
- snapshot history preservation
- MTD/YTD aggregation and prior-snapshot deltas
- freshness metadata and import audit
- unmapped SKU/data-quality exceptions

## Manual first, automate after format is stable
- THD DFC report retrieval
- THD ads exports
- Lowe's ads exports
- any portal-only source whose export behavior or schema is still changing

Automation should target stable, repetitive ingestion—not automate unstable business logic prematurely.

---

# 17. Weekly minimum input flow

Target operating day: **Tuesday**, for Wednesday weekly review.

Suggested sequence:

1. Refresh/use the official CM workbook as already required by the business process.
2. Import CM snapshot and any BP changes into STORM.
3. Export/import the shared THD + Lowe's Order report once.
4. Export/import THD DFC sell-out + inventory/WOS.
5. Export/import THD ads Campaign Performance.
6. Export/import Lowe's Campaign Summary.
7. Reuse/import Walmart normalized sales, WFS inventory, storage fee, refunds, and ads from the existing Walmart operation system where possible.
8. Run validation/reconciliation.
9. Generate Platform view, Brand × Power Source view, and SKU Exception Board.
10. Review only exceptions/data gaps before the Wednesday meeting.

Initial target incremental manual input time after reuse of existing assets: **roughly 7–12 minutes per weekly refresh**, excluding the time already required to maintain the official CM workbook. Treat this as an optimization target, not a guaranteed SLA. Measure actual elapsed time during the first 3 runs and revise.

---

# 18. Build phases

## Phase 0 — Read-only audit / mapping
Deliver:
- existing STORM table/repo map
- existing CM workbook source map
- source-to-schema mapping
- unresolved field-name mismatches

No destructive changes.

## Phase 1 — Foundation
Build:
- `DIM_SKU`
- `IMPORT_BATCH`
- `DATA_EXCEPTION`
- `FACT_BP_TARGET_MONTHLY`
- CM workbook adapter → `FACT_CM_SNAPSHOT`
- history/snapshot mechanics

Validate CM/BP extraction against the official workbook.

## Phase 2 — Primary Sales
Build:
- THD/Lowe's shared Order importer → `FACT_SALES_DAILY`
- Walmart sales adapter/reuse
- MTD/YTD aggregation
- BP attainment
- previous-snapshot deltas
- platform + Brand × Power Source views

## Phase 3 — Platform health
Build:
- THD DFC sell-through
- THD/Walmart inventory snapshot + WOS
- Walmart storage fee
- Walmart refunds
- THD/Lowe's/Walmart ads
- aligned-cutoff logic for cross-source ratios such as Walmart TACOS

## Phase 4 — Exception/control layer
Build:
- ranked SKU exceptions
- freshness warnings
- reconciliation/data-quality exceptions
- concise weekly signal generation

Do not build generalized AI narrative generation before the metrics/reconciliation layer is stable.

## Phase 5 — Automation hardening
After 2–3 successful supervised weekly runs:
- automate stable imports
- formalize file naming/source detection
- add scheduler/agent hooks only where reliable
- keep human review for unusual schema changes and data exceptions

---

# 19. Acceptance criteria

The V1 build is not accepted until all of the following hold.

## Business semantics
1. THD Primary Sales contains **sell-in only**.
2. THD DFC Sell-out is never added to Primary Sales.
3. Walmart MP Primary Sales is sell-out; WFS is inventory/fulfillment only.
4. Lowe's Primary Sales is sell-in.
5. Every Primary Sales row has an explicit `sales_basis`.
6. Walmart Owner is excluded from Structured Metrics facts.

## CM
7. STORM does not independently replace the official finance CM model.
8. Platform and Brand × Power Source CM reconcile to the intended official workbook source within a documented rounding tolerance.
9. THD Primary CM excludes DFC sell-out business from the primary sales/CM basis.
10. CM variance uses dollars and CM margin variance uses percentage points; unstable CM achievement ratios are not the primary KPI.
11. SKU-level allocated CM is not presented as direct cost attribution without evidence.

## Time
12. Every import has `snapshot_date` and source `data_through_date` where the source supports it.
13. MTD comparison uses the previous comparable snapshot from the same month.
14. New-month MTD does not compare to prior-month MTD as if it were WoW.
15. YTD comparison uses previous YTD snapshot.
16. Cross-source ratios use aligned cutoff dates.
17. Inventory is treated as snapshot data.
18. Source periods such as R30 are never relabeled MTD.

## Data quality
19. Reimporting the same file/report period is idempotent.
20. Unmapped SKUs create exceptions and are not silently dropped.
21. `N/A` is never coerced to zero.
22. Import row counts and key monetary totals are reconciled.
23. Historical snapshots are preserved.

## View behavior
24. Platform view is concise and centered on Sales + CM + one/few platform-health signals.
25. Brand × Power Source is a fixed operating view.
26. SKU is an exception/drill-down view with Platform/Brand/Power Source/SKU filters.
27. No giant all-SKU/all-metric weekly table is the default view.

---

# 20. Explicitly out of scope for V1

Do NOT build unless separately approved:
- full replacement of the official CM workbook
- a new general ledger/accounting model
- full keyword/search-term ads diagnostics inside the main cockpit
- every Walmart Operation System metric
- Walmart Owner sales/inventory metrics while control is unresolved
- universal cross-platform ROI/TACOS formulas that mix sell-in with sell-out
- a full data warehouse or generalized BI platform
- automatic business-rule thresholds invented by the implementation
- H1/H2/Q calculations copied from unverified workbook aggregate formulas

---

# 21. Required Codex deliverables

At the end of the first implementation cycle, return:

1. **Architecture implemented** — actual tables/files/views created.
2. **Source Mapping Matrix** — source report → raw fields → normalized fields → STORM table.
3. **Metric Dictionary** — formula, basis, period semantics, cutoff/alignment rules for every cockpit metric.
4. **CM Reconciliation Report** — what reconciles to the official workbook and any intentional differences, especially THD Main vs DFC.
5. **Data Quality Report** — unmapped SKUs, missing fields, rejected rows, duplicated imports.
6. **Weekly Runbook** — exact Tuesday refresh steps and measured elapsed time.
7. **Automation Backlog** — only stable repetitive steps worth automating after supervised validation.
8. **Known Limitations** — explicit, not hidden.

---

# 22. First build instruction to Codex

Start now with **Phase 0 + Phase 1 only**.

Do not jump ahead to a polished dashboard.

Your first objective is to make the data contract correct:
- canonical SKU dimensions
- BP targets
- official CM snapshots
- import batch/freshness metadata
- history preservation
- reconciliation and exceptions

After Phase 1 passes acceptance, continue with Primary Sales.

When existing project structure conflicts with this specification, do not silently choose one. Preserve existing assets and document the conflict, then choose the smallest reversible implementation that keeps the business definitions above intact.
