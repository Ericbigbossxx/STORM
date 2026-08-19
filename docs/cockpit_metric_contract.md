# STORM Cockpit Metric Contract v1

## Product and decision boundary

STORM is the North America E-commerce Business Cockpit / Weekly Business Control System.
Structured Metrics supplies evidence; it is not a finance warehouse or a replacement for
platform-owned operating systems. A metric belongs here only when it supports a cockpit fact,
signal, management judgment, or action-validation decision.

The first implementation slice is `US × WALMART_MP`. The existing Feishu tables and fields are
unchanged. Phase 2A produces a structured, dry-run Business Health payload before any external
write or UI work.

## Metric classes

| Class | Meaning |
|---|---|
| `FOUNDATION` | Authoritative source fact or approved plan required by control metrics. |
| `OPERATING` | Current platform/SKU state used during weekly review. |
| `DERIVED_CONTROL` | Deterministic comparison, attainment, coverage, or rule result. |
| `DISPLAY_ONLY` | Human-readable interpretation; cannot independently change status or create Actions. |

## Management questions and first-version metrics

### 01 Business Health — `week × market × platform`

| Management question | Metrics | Decision use |
|---|---|---|
| Are sales progressing toward plan? | Actual Sales, BP Sales, Sales Attainment % | Sales Health context and weekly priority. |
| Is CM progressing toward plan? | Actual CM, BP CM, CM Attainment %, CM % | Economic-health context; never substitute Walmart contribution profit without semantic approval. |
| Is performance improving or deteriorating? | Sales Comparable Change % | Top Change; only from comparable official snapshots. |
| Is advertising efficient? | Ad Spend, Attributed Ad Sales, ROAS | Ads Health context and review prioritization. |
| Is inventory constraining sales or creating exposure? | Inventory Condition | Inventory Health; platform rollup rule remains contract-only. |
| Is evidence safe to compare? | Freshness State, Comparison Through Date | Data Completeness, Data As Of, and evidence warnings. |
| What needs management attention? | Overall Business Status, Management Interpretation | Overall Health, Top Risk, Top Opportunity, Next Priority. |

Sales/CM attainment is explicitly MTD progress against a full-month target. It is not a
plan-to-date pacing metric because no authoritative daily target curve exists. No
GREEN/YELLOW/RED threshold is invented in v1.

### 02 Core SKU Performance — `week × platform × canonical_sku`

| Management question | Metrics | Decision use |
|---|---|---|
| What sales scale and plan progress does the SKU have? | SKU Actual Sales, SKU BP Sales, SKU Sales Attainment % | Sales, Target, Target Gap %. |
| Is advertising helping? | SKU Ad Spend, Attributed Ad Sales, ROAS | Ad Spend, ROAS, Diagnosis. |
| Is inventory or availability constraining the SKU? | SKU Inventory Condition; Availability=`SOURCE_NOT_AVAILABLE` | Inventory, Buyability, Status. |
| Is the SKU economically healthy? | Actual CM/CM % where source grain is verified | Diagnosis/Evidence; no new Feishu field. |
| What role does the SKU play? | SKU Business Role | SKU Role and review context. |
| What issue and action require review? | SKU Primary Issue, SKU Required Action | Main Change, Diagnosis, existing governed Action link/text. |

Only core, exception, or current-focus SKUs belong in the Feishu table. Missing SKU facts remain
blank/UNKNOWN and do not generate a default recommendation.

### 03 Action & Validation

The cockpit can supply an approved baseline metric, comparable actual result, and
`Action Validation Delta`. It may update a dry-run validation payload only when the metric,
validation window, and common cutoff are explicit. Execution is not validation. Human Decision
remains final; no Action is created or executed automatically.

### 04 Signal Register

`Signal Eligibility` means an approved deterministic rule has sufficient current evidence.
Phase 2A may emit a dry-run candidate with the triggering metric, rule version, cutoff, and
evidence. It does not create a live Signal. Missing evidence makes the candidate ineligible; it
does not imply GREEN.

## Source authority

| Evidence | Authority | STORM use |
|---|---|---|
| Monthly SKU BP | `KPI Rawdata` → `FACT_BP_TARGET_MONTHLY` | Authoritative BP at SKU; aggregate to Brand×Power/platform. |
| Actual CM | Verified `Overview` Actual CM detail → `FACT_CM_SNAPSHOT` | Authoritative MTD CM; THD Main sell-in only, DFC excluded. |
| Overview BP | Workbook derived view | Secondary warning/check only. |
| Walmart sales, advertising, inventory and SKU operating state | Walmart Operation System official release manifest and canonical snapshots | Read-only platform evidence through a thin STORM adapter. |
| Human status/interpretation/action validation | Existing four Feishu tables | Final control-plane authority; no schema change. |

Walmart Operation System `contribution_profit` is not automatically renamed to STORM `CM`.
The v1 Walmart Actual CM remains the verified CM workbook fact unless a later cockpit decision
explicitly approves semantic equivalence.

## Time semantics

`control_week` is the management-review bucket and the structured cockpit grain. It does not
describe any source measurement window. The existing Feishu `Week` field stores this
`control_week` value; it is not renamed because Phase 2B does not change the live schema.
Generic structured payload field `week` is retired to prevent the control bucket from being
confused with a native source week.

Every fact or payload metric carries concepts equivalent to:

- `snapshot_date`: when the snapshot was captured or accepted;
- `data_through_date`: last date represented by the metric;
- `period_start` and `period_end`: native coverage boundaries;
- `period_type`: MTD, WEEKLY, MONTHLY_TARGET, SNAPSHOT, or another contracted type;
- `import_batch_id`: immutable lineage to the accepted import/release;
- optional `source_generated_at` and `source_timezone` when supplied.

Existing fields are reused. For Phase 1 BP, period start/end derive from year/month. For CM MTD,
period start is the first of the selected month and period end equals `data_through_date`; no
schema expansion is required for the closeout.

For a multi-source metric:

```text
comparison_through_date = min(participating source data_through_date)
```

This rule is valid only when every participating source can be sliced or is already aggregated
to that common date. Merely relabeling a broader aggregate with an earlier date is forbidden;
the comparison is `NOT_COMPARABLE` when aligned values cannot be produced. Native fresher facts
remain visible. If sales is through August 10 and ads through August 9,
the cross-source comparison stops at August 9 while native sales still displays August 10.

## Freshness and coverage vocabulary

| State | Definition |
|---|---|
| `CURRENT` | Latest evidence expected under a reviewed source cadence. |
| `LAGGING` | Behind another source but still consistent with its normal reviewed cadence. |
| `STALE` | Missed an expected refresh under a reviewed cadence. |
| `SOURCE_NOT_AVAILABLE` | Required source/snapshot is absent or not authoritative. |
| `NOT_APPLICABLE` | Metric does not apply to the platform/SKU/use case. |

No numeric freshness threshold is defined until the platform source cadence is reviewed. MTD
acceptance does not manufacture YTD: current CM workbook coverage is
`MTD=ACCEPTED`, `YTD=SOURCE_NOT_AVAILABLE`.

## Feishu destination without schema changes

The internal dry-run payload separates `facts`, `data_status`, `derived_control_metrics`, and
`interpretation`. Existing `01 Business Health` receives status, summaries, cutoffs, source
references, risks, opportunities, and next priority. Existing `02 Core SKU Performance` receives
its already-supported numeric fields. CM and other unsupported numerics remain in structured
payload/Evidence/summary; no new Feishu fields are created. Human Reviewed remains false unless
the human workflow approves it.

The complete machine-readable field-by-field contract is
`config/cockpit_metrics.yaml` and includes definition, question, authority, grain, period,
source, calculation, NULL behavior, freshness, destination, Signal eligibility, Action
validation eligibility, classification, and Phase 2A status for every proposed metric.
