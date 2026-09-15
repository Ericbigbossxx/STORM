# Phase 1 Closeout + Phase 2A Walmart Cockpit Checkpoint

Status: `PHASE_2A_ACCEPTANCE = ACCEPTED` (local dry-run vertical slice only)

## 1. Phase 1 closeout

### Reconciliation root cause

Classification: `BROKEN_DERIVED_FORMULA`.

The official workbook was inspected with formulas and cached values separately. The formula
chain for Walmart MP / Sunseeker / Robot is:

```text
Overview!P300
  SUMIFS KPI Rawdata Qty
  where KPI Rawdata.Customer = Overview!P296

Overview!P296 = Overview!P258 = "Walmart"
authoritative KPI Rawdata.Customer = "Walmart Seller"
```

The parallel Badger column uses `Z258 = "Walmart Seller"` and returns 44 units. The zero
Sunseeker result is therefore not a stale cache and not a disagreement between authoritative
sources; it is a broken customer-display mapping in the secondary Overview BP formula.
The workbook was not edited.

### Source authority and acceptance

| Item | Status | Evidence/rule |
|---|---|---|
| Authoritative monthly BP | `ACCEPTED` | `KPI Rawdata` → 1,110 monthly SKU facts. Overview BP is secondary only. |
| Authoritative Actual CM | `ACCEPTED` | Verified Overview Actual CM detail and platform reconciliation. |
| THD primary CM | `ACCEPTED` | Main sell-in only; DFC excluded without weakening. |
| MTD foundation | `PHASE_1_MTD = ACCEPTED` | Batch `5a7ee7c5-4895-4243-b771-39143bc42011`, 1,218 loaded rows, zero rejected rows, zero blocking reconciliation failures. |
| Derived BP view | `PASS_WITH_WARNINGS` | Six `BROKEN_DERIVED_FORMULA` warnings plus one normalized duplicate-SKU warning. |
| YTD coverage | `SOURCE_NOT_AVAILABLE` | Workbook is saved at MTD; no YTD reconstruction or manufactured cache. |

The runtime database is ignored at
`data/structured_metrics/storm_metrics.sqlite3`. Current accepted counts are one import batch,
93 `DIM_SKU`, 1,110 monthly BP facts, 15 CM snapshots, and seven warnings.

Phase 1 CM enhancement stops here. No new finance calculation, dimension, forecast, workbook
manipulation, or finance-engine behavior is proposed.

## 2. Cockpit metric contract

The complete contract is in `docs/cockpit_metric_contract.md`; machine-readable definitions are
in `config/cockpit_metrics.yaml`.

### First-version metric set

| Management question | Proposed metrics | Phase 2A use |
|---|---|---|
| Are sales progressing toward plan? | Actual Sales, BP Sales, Sales Attainment % | Business Health facts and Sales Health context. |
| Is CM progressing and economically healthy? | Actual CM, BP CM, CM Attainment %, CM % | Business Health facts; CM source remains distinct from Walmart contribution profit. |
| Is the platform improving or deteriorating? | Comparable Weekly Sales Change | Use consecutive comparable `WEEKLY_OPERATING` snapshots, not cross-month MTD reset. |
| Is advertising efficient? | Ad Spend, Attributed Ad Sales, ROAS | Ads Health context and SKU review evidence. |
| Is inventory constraining sales or creating exposure? | Inventory Condition and units/status distribution | Minimal indicator only; no forecasting or warehouse. |
| Are sources current and comparable? | Freshness State, native cutoffs, Comparison Through Date/status | Expose CURRENT/LAGGING/STALE/NOT AVAILABLE and prohibit false alignment. |
| What needs management attention? | Overall Status, Primary Driver, Key Risk, Key Opportunity, Required Action | Minimal deterministic summary plus human review. |
| Which SKU needs attention and why? | SKU sales/BP/attainment, ads/ROAS, inventory, availability, CM where verified, role, issue, action | Populate only core/exception/focus SKU payloads. |
| Did an action work? | Approved baseline, actual result, validation delta | Comparable-window evidence for existing Action lifecycle; no auto-validation. |
| Should evidence be reviewed as a Signal? | Signal Eligibility | Dry-run candidate only under approved rules; no automatic Signal creation. |

No health threshold, freshness-day threshold, advertising target, reorder rule, or autonomous
recommendation is added. Missing facts remain NULL/UNKNOWN.

## 3. Walmart Operation System reuse assessment

The checkout `C:\Users\admin\Documents\Walmart Operation System` was inspected read-only.
Its working tree was clean on `feature/phase2-strategy-performance`; no file was modified.

### Current verified release

- Release manifest: `outputs/latest/backend_release_manifest.json`.
- Release/run: `20260804_151643_WEEKLY`, `SUCCESS`, `READY_FOR_PHASE_3`.
- Business date: 2026-08-02; generated 2026-08-04 07:16:43 UTC.
- Existing `UIDataService` validation returned no schema, primary-key, or content-hash errors
  for business MTD, business weekly, YTD baseline, SKU MTD, decision state, snapshot manifest,
  data quality, business trend, and SKU trend.
- Latest direct results: Business MTD 1 row through 2026-08-02; Business Weekly 1 row for
  2026-07-27–2026-08-02; SKU MTD 55 rows; Decision 55 rows; Snapshot Manifest 7 latest rows.
- `PRODUCT_LINE_NOT_AVAILABLE` is a warning on current SKU/decision datasets and must not be
  invented by STORM.

### Reuse directly

| Asset | Reuse |
|---|---|
| `config/backend_data_contract.yaml` | Canonical dataset ownership, allowed roots, keys, and read-only boundary. |
| `config/backend_schema_versions.yaml` | Field requirements, nullability, enums, and semantic-version contract. |
| `outputs/latest/backend_release_manifest.json` | Official run selection, readiness, content hashes, business dates, and lineage. |
| `data/history/marketplace/business_mtd_snapshots.parquet` | Walmart MTD sales, ads, contribution-profit context, inventory units, action counts. |
| `data/history/marketplace/business_weekly_snapshots.parquet` | Comparable weekly operating facts; use matching coverage windows. |
| `data/history/marketplace/sku_mtd_snapshots.parquet` | SKU sales, ads, ROAS, inventory, status, source dates and quality fields. |
| `data/processed/decision_engine_mtd_output.parquet` | Governed SKU role/status context; human/manual fields remain authoritative. |
| `data/history/marketplace/multi_period_snapshot_manifest.parquet` and official run manifest | Publication, supersession, hashes, source file coverage, and generated timestamps. |
| Effective Action registry/event history | Read-only Action/validation context only when a cockpit use case needs it. |

### Reuse through a thin adapter

- Resolve only the official run named by the release manifest.
- Enforce the Walmart contract's allowed roots and reject raw, fixture, failed, non-official,
  superseded, or out-of-scope sources.
- Validate release/pipeline/readiness status, schema version, primary key, record count, and
  content hash before returning evidence.
- Translate Walmart `Marketplace 3P` to STORM `WALMART_MP`, normalize date/time lineage, and
  preserve NULLs and source statuses.
- Select only fields required by `config/cockpit_metrics.yaml`; do not import the entire 53/87
  column SKU/decision models.

Do not import or depend directly on `src/ui/data_service.py`: it is a 122 KB Streamlit-facing
service with presentation/ranking logic. Its manifest-first validation pattern is reusable,
but STORM needs a small platform adapter without Streamlit or UI scoring dependencies.

### Remain owned by Walmart Operation System

- Raw/staging ingestion, report matching, DDP/cost/fee logic, refunds, ad normalization,
  inventory normalization, protected publication, History, manifests, and hashes.
- Walmart-specific decision scoring, Action lifecycle engine, seasonality configuration,
  Streamlit pages, rankings, and display-only composite scores.
- The distinction among YTD, MTD, weekly, and advertising source periods.

STORM must not copy these pipelines, recalculate Walmart contribution profit, or read raw data.

### STORM ownership

- Cross-platform cockpit metric contract and platform adapter boundary.
- Native cutoff/freshness representation and comparable-period eligibility.
- Joining accepted BP/CM measurement facts with platform-owned operating evidence only when
  definitions and dates are compatible.
- Business Health/Core SKU dry-run payloads, minimal deterministic interpretation, and mapping
  to the existing Feishu control plane.
- Human authority, Signal eligibility, and Action validation evidence boundaries.

### Reuse risks found

1. The latest Walmart MTD operating snapshot ends 2026-08-02, while the accepted CM snapshot
   ends 2026-08-10. Both may be displayed with native dates, but a combined calculation is
   `NOT_COMPARABLE` unless each source can be sliced to a common cutoff. The aggregated CM fact
   cannot currently be trimmed to August 2.
2. `weekly_business_trend` currently contains an MTD row comparing August 1–2 against July
   1–26 while reporting a seven-day snapshot interval. STORM must use consecutive
   `business_weekly_snapshots` for weekly improvement/deterioration, not treat the cross-month
   MTD reset as a comparable WoW result.
3. Walmart `contribution_profit` and workbook `Actual CM` have different owners/definitions.
   They remain separate until a reviewed semantic mapping exists.
4. Inventory value, buyability, and a reviewed platform-level inventory health rollup are not
   available for this slice. They must remain unavailable/contract-only.

## 4. Minimal Phase 2A implementation plan

No new fact table is justified yet. The smallest implementation after approval is:

1. Add `config/walmart_official_source.yaml` with the local root, manifest path, allowed dataset
   names, platform mapping, and read-only policy. It contains no token or business export.
2. Add `src/storm/adapters/walmart_official/adapter.py` to read only official manifest-selected
   Parquet/JSON assets, enforce contract/hash/schema/key gates, and return a narrow normalized
   evidence object. Do not import Walmart UI code or raw pipeline modules.
3. Add `src/storm/cockpit/models.py` for `facts`, `data_status`, `derived_control_metrics`, and
   `interpretation` payload contracts with explicit time lineage.
4. Add `src/storm/cockpit/business_health.py` to assemble one `US × WALMART_MP` dry-run snapshot
   from the accepted Structured Metrics database and verified Walmart evidence. Compute only
   sales/CM attainment, ROAS, and comparable-period eligibility defined by the metric contract.
5. Add a dry-run mapper matching the existing `01 Business Health` schema. Numeric details not
   represented by Feishu remain in the structured payload/summary/evidence. No live write.
6. Add focused tests for official-run selection, forbidden sources, hash/schema/key failure,
   NULL preservation, mismatched cutoff non-comparability, month-reset protection, payload
   structure, and unchanged Feishu schema.

This plan adds one adapter and one small assembly layer, not a new warehouse. Full SKU payload,
Signal candidate, and Action validation can follow only after the Business Health slice proves
the pipeline and receives separate authorization.

## 5. Scope check

`This work directly supports the STORM cockpit and does not expand STORM into a general-purpose finance/data warehouse.`

## 6. Phase 2A implementation closeout

The approved vertical slice is implemented with no Feishu write and no schema change:

- `config/walmart_official_source.yaml` limits access to the four approved official datasets.
- `src/storm/adapters/walmart_official/adapter.py` enforces release, path, schema, key, count,
  content-hash, publication, supersession, and lineage gates.
- `src/storm/cockpit/` assembles one `week × US × WALMART_MP` snapshot and maps an exact-field
  `01 Business Health` dry-run payload.
- `scripts/build_phase2a_walmart_cockpit.py` creates the ignored local JSON and Markdown
  artifacts under `data/cockpit/phase2a/`.
- Focused Phase 2A tests and the full project suite pass. No Structured Metrics table was added.

Current native cutoffs remain explicit: Walmart sales/ads/inventory through 2026-08-02 and
accepted CM through 2026-08-10. A combined common-cutoff metric is `NOT_COMPARABLE`; YTD CM is
`SOURCE_NOT_AVAILABLE`; health and management interpretation remain `UNKNOWN`/`UNRESOLVED`.

`PHASE_2A_ACCEPTANCE = ACCEPTED`
