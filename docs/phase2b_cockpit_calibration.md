# STORM Phase 2B — Walmart Cockpit Calibration & Control Contract

Status: `PHASE_2B_REVIEW_READY — RULE_AND_SCHEMA_APPROVAL_REQUIRED`

## Executive summary

- The Walmart vertical slice is semantically usable after one labeling/time-contract
  calibration. `Actual Sales = -694.21` is official August MTD **net sales**, not a mapping
  error. Official evidence reconciles `358.79 Auth Sales - 1,053.00 Refund sales = -694.21`.
- The structured grain is now explicit as `control_week × market × platform`. Every metric
  retains its own measurement period and cutoff; `control_week=2026-W33` does not imply that
  every source measures week 33.
- The `-78.82%` weekly trend is valid: it compares two consecutive, official, non-superseded,
  seven-day `WEEKLY_OPERATING` windows using the same net-sales definition. No MTD month reset
  participates.
- No current health color is authorized. Rules v1 is a proposal only. The minimum proposed
  Feishu delta is two fields—`CM Health` and `Data Confidence`—not fourteen numeric fields.

## 1. Business semantic audit

`Safe` means the displayed value and label support the stated management interpretation. A
metric may be safe with a required caveat and still be ineligible for an unapproved health rule.

| STORM metric | Source artifact and exact fields | Definition, period and source grain | Data through and transformation | Semantic conclusion |
|---|---|---|---|---|
| `actual_sales` | Walmart `business_mtd_snapshots.parquet.net_sales`; upstream August `ItemSales...xlsx` maps `GMV → net_sales`, `Auth Sales → gross_sales`, `Refund sales → sales_refund_amount` | Refund-inclusive Walmart Marketplace net sales; `MTD_OPERATING`; upstream SKU×MTD, aggregated to platform | 2026-08-02; sum of current exact-period SKU `net_sales` | **Safe when labeled Net Sales.** `SEMANTICALLY_VALID`. |
| `bp_sales` | Structured Metrics `FACT_BP_TARGET_MONTHLY.bp_sales`; workbook `KPI Rawdata.TTL amount` | Approved full-month sell-out sales target; SKU×month×platform, aggregated across 37 Walmart SKUs | Target month 2026-08-01–2026-08-31; nullable sum | **Safe as Full-month BP Sales Target.** It is not plan-to-date. |
| `sales_attainment_pct` | `actual_sales`, `bp_sales` | MTD net-sales progress against the full-month target; platform×control review | `-694.21 / 207,511.70 = -0.3345%`; actual cutoff 2026-08-02 | **Safe with caveat.** Valid cumulative progress, not pacing. Confirm the BP target's reviewed net-vs-gross basis before activating a health rule. |
| `actual_cm` | Structured Metrics `FACT_CM_SNAPSHOT.actual_cm`; workbook `Overview` Actual CM detail | Accepted primary contribution margin; Brand×Power Source×MTD, aggregated to platform | 2026-08-10; nullable sum of five Walmart facts | **Safe.** Separate from Walmart Operation System `contribution_profit`. |
| `bp_cm` | `FACT_BP_TARGET_MONTHLY.bp_cm`; `KPI Rawdata` CM components | Approved full-month CM target; SKU×month×platform | Target month through 2026-08-31; nullable sum | **Safe as Full-month BP CM Target.** Authoritative KPI Rawdata is used; broken Overview BP is not. |
| `cm_attainment_pct` | `actual_cm`, `bp_cm` | MTD CM progress against full-month CM target | `-3,273.3247 / 15,518.4739 = -21.0931%`; actual cutoff 2026-08-10 | **Safe with progress—not pacing—label.** |
| `actual_cm_pct` | `FACT_CM_SNAPSHOT.actual_cm`, `.actual_sales` (`cm_basis_sales`) | CM rate on the same accepted CM sell-out basis and batch | `-3,273.3247 / 5,750.92 = -56.9183%`; through 2026-08-10 | **Safe.** It must not use Walmart `net_sales=-694.21`, whose cutoff and owner differ. |
| `ad_spend` | Walmart `business_mtd_snapshots.parquet.ad_spend`; upstream `ItemPerformance...csv.Ad Spend` | Official attributed-ad MTD spend; SKU-period aggregate rolled to platform | 2026-08-02; sum = 221.63 | **Safe.** |
| `attributed_ad_sales` | `.ad_sales`; upstream `Total Attributed Sales` | Official MTD advertising-attributed sales; same ad period and grain as spend | 2026-08-02; sum = 0.00 | **Safe.** Zero is source-reported, not missing-data substitution. |
| `roas` | `.calculated_roas` from `.ad_sales/.ad_spend` | Advertising return on attributed sales | `0.00 / 221.63 = 0.00`; through 2026-08-02 | **Safe.** No health judgment exists without an approved target and attribution rule. |
| `inventory_units` | Walmart `business_mtd_snapshots.parquet.inventory_units`; upstream Inventory `Available Units` | Available units, not total owned inventory or inventory value; mapped SKU snapshot aggregated to platform | Snapshot 2026-08-02; sum = 884 | **Safe with label Available Units.** Raw platform total alone is not a health rule. |
| In Stock count | Walmart `sku_mtd_snapshots.parquet.inventory_status` and `inventory_data_status` | Count of current SKU snapshot rows with status `In Stock`; SKU×snapshot | 2026-08-02; 29 rows; 884 available units | **Safe.** Status is source-reported where present or derived from positive available units. |
| Out of Stock count | Same fields | Count of `Out of Stock` rows with available evidence | 2026-08-02; 22 rows; zero available units | **Safe.** It does not establish business materiality without SKU role/sales weight. |
| Not Applicable count | Same fields | Seller-fulfilled/no applicable WFS inventory state under source rules | 2026-08-02; 4 rows | **Safe.** Must remain separate from missing and OOS. |
| `weekly_sales_change` | Walmart `business_weekly_snapshots.parquet.net_sales`, coverage fields, period scope and Snapshot Manifest | Change between consecutive exact seven-day official business net-sales windows | `(447.97 - 2,115.52) / abs(2,115.52) = -78.8246%`; current through 2026-08-02 | **Safe.** See the dedicated validation below. |

### Exact conclusion for `Actual Sales = -694.21`

1. **Canonical source artifact:** `data/history/marketplace/business_mtd_snapshots.parquet`,
   official run `20260804_151643_WEEKLY`.
2. **Canonical field:** `net_sales`; upstream August ItemSales source maps Walmart `GMV` to
   normalized `net_sales`.
3. **Raw official aggregate:** `-694.21` for 2026-08-01 through 2026-08-02.
4. **Refund behavior:** refunds are included. Official aggregates are Auth/Gross Sales `358.79`,
   Refund Sales `1,053.00`, and Net Sales `-694.21`.
5. **Period:** true current-month MTD for August 1–2, selected from the exact-period ItemSales
   input. The July ItemSales file is not included.
6. **Semantic:** refund-inclusive net sales/revenue. It is not gross sales, profit, contribution
   margin, or a computed week-over-week delta.
7. **Negative-value support:** genuine official source evidence. The official run manifest shows
   preflight and formal input both `-694.21`, difference `0.00`, status `PASS`.
8. **BP compatibility:** compatible only as deliberately defined
   `MTD net-sales progress / full-month sell-out target`. It is not period-aligned plan-to-date
   pacing. Before activating a health rule, management must confirm the BP `TTL amount` target's
   reviewed net/gross treatment or approve this comparison basis explicitly.

Classification: **`SEMANTICALLY_VALID`**. The negative value is a business exception caused by
refunds exceeding authorized sales, not a source-data or mapping defect. No value correction is
made.

## 2. Control time and measurement time

The platform row uses this control identity:

```text
control_week = 2026-W33
market       = US
platform     = WALMART_MP
level        = PLATFORM
```

`control_week` means the management review bucket. Feishu retains its existing field name
`Week`, but STORM maps `control_week → Week`. Structured payloads no longer use a generic `week`
field.

Every metric separately carries:

```text
period_type
period_start
period_end
data_through_date
snapshot_date
source release/import lineage
```

For the current control week, sales/ads/inventory end 2026-08-02, weekly trend ends 2026-08-02,
and CM ends 2026-08-10. These dates coexist; STORM does not relabel them to the control week or
manufacture a common cutoff.

## 3. Weekly trend validation

| Check | Prior window | Current window | Result |
|---|---|---|---|
| Period scope | `WEEKLY_OPERATING` | `WEEKLY_OPERATING` | Pass |
| Coverage | 2026-07-20–2026-07-26 | 2026-07-27–2026-08-02 | Pass: consecutive 7-day windows |
| Metric scope | `BUSINESS_WEEKLY.net_sales` | `BUSINESS_WEEKLY.net_sales` | Pass: same definition/grain |
| Official run | `20260728_115642_WEEKLY` | `20260804_151643_WEEKLY` | Pass: both registered official, published and non-superseded |
| Net sales | 2,115.52 | 447.97 | Comparable |
| Month reset | Not an MTD comparison | Not an MTD comparison | Pass: no contamination |

Formula:

```text
absolute change = 447.97 - 2,115.52 = -1,667.55
percent change  = -1,667.55 / abs(2,115.52) = -78.8245916%
```

The older 2026-07-19 row in the history file belongs to a superseded run and is excluded by the
adapter. Conclusion: **retain `Weekly Sales Change = -78.82%`.**

## 4. Feishu gap analysis

Category A is `CONTROL_PLANE_REQUIRED`; B is `DIAGNOSTIC_ONLY`; C is
`REDUNDANT_OR_NOT_REQUIRED`.

| Unmapped metric | Management question | Category | Existing destination | New numeric field needed? |
|---|---|---|---|---|
| `actual_sales` | What net sales have been realized? | A | `Weekly Summary` | No |
| `bp_sales` | What is the monthly sales target? | A | `Weekly Summary` | No |
| `sales_attainment_pct` | What share of the monthly target is realized? | A | `Weekly Summary`; supports `Sales Health` after approval | No |
| `actual_cm` | What CM has been realized? | A | `Weekly Summary` | No |
| `bp_cm` | What is the monthly CM target? | A | `Weekly Summary` | No |
| `cm_attainment_pct` | What share of monthly CM target is realized? | A | `Weekly Summary`; future `CM Health` | No |
| `actual_cm_pct` | Is the current CM rate economically acceptable? | A | `Weekly Summary`; future `CM Health` | No |
| `ad_spend` | How much has been spent? | A | `Weekly Summary`; `Ads Health` after approval | No |
| `attributed_ad_sales` | What attributed revenue did spend produce? | A | `Weekly Summary` | No |
| `roas` | Is advertising efficient versus an approved target? | A | `Weekly Summary`; `Ads Health` after approval | No |
| `inventory_units` | What available-unit scale underlies the status? | B | Structured evidence and optional summary context | No |
| `inventory_condition` | How many SKUs are In Stock/OOS/N/A? | A | `Weekly Summary`; `Inventory Health` after approval | No |
| `weekly_sales_change` | Is the platform improving or deteriorating? | A | `Top Change` | No |
| `ytd_actual_cm` | Is YTD CM evidence available? | B | `Data Completeness`/source diagnostics; currently unavailable | No |

No metric is Category C in the current fourteen, but Category A does not imply a dedicated
Feishu number field. Feishu remains a control ledger, while structured numeric evidence remains
in the local cockpit snapshot and concise narrative fields.

### Minimum proposed Feishu schema delta

Proposal only—do not execute:

1. Add `CM Health` as a single select with `GREEN/YELLOW/RED/UNKNOWN` so profitability is not
   hidden inside Sales or Overall Health.
2. Add `Data Confidence` as a single select with `HIGH/MEDIUM/LOW/UNKNOWN`, separate from
   `Overall Health`. Keep existing `Data Completeness`; completeness is an input, not the whole
   confidence judgment.

No dedicated fields are proposed for the fourteen numeric/diagnostic metrics. Schema delta:
**two fields**, pending explicit approval and live reconciliation.

## 5. Business Health Rules v1 proposal

Machine-readable proposal: `config/business_health_rules_v1_proposal.yaml`. It is inactive and
cannot assign current colors.

| Rule | Management meaning and required metrics | Eligibility | Decision-boundary proposal | Threshold source and unavailable behavior |
|---|---|---|---|---|
| Sales Health | Is net sales progressing toward monthly BP? Actual, BP, attainment, comparable weekly trend | Compatible reviewed sales basis; same target month; official trend if used; evidence not stale | GREEN/YELLOW/RED based on an approved pacing floor, tolerance band and material decline rule | No pacing curve/bands exist. `PENDING_MANAGEMENT_APPROVAL`; otherwise `UNKNOWN`. |
| CM Health | Are CM amount and CM% progressing acceptably? Actual CM, BP CM, CM attainment, CM% | Actual CM and basis sales from same batch; BP same month/platform; evidence not stale | Approved amount pacing plus target CM% and critical-loss boundary | BP can anchor target; pacing/critical boundaries require approval. Otherwise `UNKNOWN`. |
| Ads Health | Is spend producing sufficient attributed sales? Spend, attributed sales, ROAS | Same official ad period; attribution available; evidence not stale | Approved ROAS target/review band and material-spend floor | No target or attribution-completeness rule exists. Otherwise `UNKNOWN`. |
| Inventory Health | Is OOS or excess exposure materially affecting the business? Available units and status distribution | Status coverage available and tied to reviewed SKU/sales materiality | Approved core-SKU/OOS or exposure boundary | Raw OOS count is not a materiality threshold. No excess/aging evidence exists; otherwise `UNKNOWN`. |

The proposed preview displays `PENDING_RULE_APPROVAL`, not a color, because evidence exists but
authorization does not. Genuine missing evidence continues to use `SOURCE_NOT_AVAILABLE`.

## 6. Overall health and data confidence

`business_health` and `data_confidence` are independent outputs.

### Business health

- Do not average colors or convert them to scores.
- Sales and CM are primary controls; Ads and Inventory are contextual controls.
- An approved material RED may dominate, but the materiality/dominance policy must be explicit.
- Missing or ineligible data never becomes GREEN.
- Until domain rules and dominance policy are approved, Overall Health remains
  `PENDING_RULE_APPROVAL` in Preview v2 and `UNKNOWN` in the existing dry-run Feishu record.

### Data confidence

- Proposed states: `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`.
- Inputs: manifest/hash/schema/PK validation, availability, freshness, cutoff compatibility and
  lineage completeness.
- Poor business performance can have HIGH data confidence. Missing/stale evidence can lower
  confidence without implying bad performance.
- The current preview shows factual `Data Coverage: PARTIAL`, not an activated Data Confidence rule:
  lineage is validated, cutoffs differ, and YTD CM is unavailable.

## 7. Management interpretation contract

| Field | Machine role | Existing records | Human role | Authority |
|---|---|---|---|---|
| Primary Driver | Identify the largest approved deterministic rule deviation and cite evidence | May reference approved Signal/Action evidence | Confirm or override with rationale | Hybrid; human final |
| Key Risk | Surface an approved deterministic risk candidate | Prefer an existing approved Signal when one exists | Select and finalize wording | Hybrid; human final |
| Key Opportunity | Surface an approved deterministic opportunity candidate | Prefer an existing approved Signal when one exists | Select and finalize wording | Hybrid; human final |
| Required Action | Link evidence or request human review only | Display/link an existing approved Action | Define/approve action, owner and timing | Human or existing approved Action only |

No autonomous LLM recommendation, Signal creation or Action creation is allowed.

## 8. Cockpit Preview v2

Generated artifact: `data/cockpit/phase2b/walmart_cockpit_preview_v2.md`.

The preview uses management sections—Performance, Profitability, Advertising, Inventory, Data
Coverage and Control. It labels `-694.21` as Net Sales, separates Control Week from every native
cutoff, shows YTD CM as `SOURCE_NOT_AVAILABLE`, and uses `PENDING_RULE_APPROVAL` for unapproved
control judgments.

## 9. Cross-platform replication boundary

### COMMON STORM

- `control_week × market × platform` cockpit key and metric-level measurement-time model.
- Fact, data-status, derived-control and interpretation payload structure.
- Freshness/availability vocabulary, cutoff compatibility, NULL behavior and lineage contract.
- Comparable-week interface and month-reset protection.
- Business Health rule interface, rule eligibility, overall precedence and data-confidence
  separation.
- Feishu dry-run mapping, preview structure, human authority and no-write boundary.

### PLATFORM ADAPTER

- Official release discovery and validation.
- Native source fields, period definitions, keys, hashes and null/status normalization.
- Platform code/name mapping and evidence lineage.
- Platform sales, advertising and inventory source selection.

### PLATFORM-SPECIFIC BUSINESS RULE

- What constitutes net/gross sales and whether BP uses an equivalent basis.
- CM ownership/basis and any platform-specific exclusions.
- Advertising attribution completeness, target/break-even ROAS and spend materiality.
- Inventory applicability, fulfillment-specific status, core-SKU/OOS materiality and
  excess/aging rules.
- Reviewed refresh cadence and any threshold justified by platform history.

This boundary indicates that THD/Lowe's should mostly require adapters plus explicitly approved
platform rules, not a redesign of STORM. No such adapter or rule is implemented in Phase 2B.

## 10. Files changed and tests

Phase 2B changes are limited to:

- renaming the structured payload time key from ambiguous `week` to `control_week` and mapping it
  to the unchanged Feishu `Week` field;
- adding the inactive rules proposal;
- adding a reproducible Preview v2 builder and management-oriented preview renderer;
- adding this calibration report and focused regression tests.

No source metric value, Feishu schema, live record, database table, THD/Lowe's adapter, Signal,
Action, UI or health threshold is changed or activated.

Acceptance evidence:

- Full project suite: `63 passed`.
- Preview v2 was rebuilt twice with identical snapshot and Markdown SHA-256 hashes.
- The self-contained HTML report passed canonical artifact validation plus exact embedded-payload,
  runtime-root and semantic-fallback structural verification (`15` blocks, `4` metric cards, `1`
  native chart and `3` native tables).
- Visual QA confirmed the report content, chart and tables render. The installed portable reader has
  a known Windows browser-verifier defect: its sticky top bar uses `100vw` while the vertical
  scrollbar is present, producing an 8 px document-level horizontal-overflow warning. The two
  reported elements are reader chrome, not report content; no project or global plugin code was
  changed to mask it.

## Approval checkpoint

Phase 2B stops at:

`PHASE_2B_REVIEW_READY — RULE_AND_SCHEMA_APPROVAL_REQUIRED`

Separate explicit approval is required before any Feishu schema delta or Business Health rule
activation.
