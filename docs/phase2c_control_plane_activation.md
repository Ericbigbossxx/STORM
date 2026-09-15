# STORM Phase 2C — Control Plane Activation

Status: `PHASE_2C_BLOCKED`

The local deterministic rule engine, Walmart snapshot v3, Preview v3, Feishu mapping review and
live-write candidate are complete. The first Feishu record write was not attempted. The approved
two-field live schema delta is blocked because this session has no runtime Base `app_token`; the
identifier was not guessed, recovered from historical logs or persisted.

## 1. Feishu schema before / after

### Last-known local checkpoint

- Base: `STORM | Business Control`
- Target table: `01 Business Health` (`tblCw58AnpOBjQOZ`)
- Target-table fields: `29`
- Total Base fields: `125`
- Tables / views / records at the manifest checkpoint: `4 / 13 / 26`
- `CM Health`: absent
- `Data Confidence`: absent

### Approved candidate delta

| Field | Type | Options |
|---|---|---|
| CM Health | single select | GREEN, YELLOW, RED, UNKNOWN |
| Data Confidence | single select | HIGH, MEDIUM, LOW, UNKNOWN |

Expected post-change counts are `31` target-table fields and `127` total fields. No other table,
field, view or record is in the candidate delta.

### Live result

`NOT_APPLIED — RUNTIME_BASE_TOKEN_UNAVAILABLE`

Live field-list inspection, field creation and post-change reread could not be invoked without the
Base token required by the Feishu MCP methods. The canonical live manifest remains unchanged so it
does not falsely claim field IDs or live counts that were never verified.

## 2. Activated Business Health Rules v1

Rules v1 is active only in the explicit Phase 2C build path. It is deterministic, uses no LLM
judgment and cannot write records. Every evaluation retains the input values, eligibility, exact
rule/formula, reason, result and source lineage.

- Sales: negative Actual Sales hard RED; otherwise 95%/80% attainment bands; valid weekly decline
  at or below -25% can only downgrade one level.
- CM: negative Actual CM or CM% hard RED; otherwise 95%/80% attainment bands after authoritative,
  period-compatible same-batch reconciliation.
- Advertising: positive spend with zero attributed sales is RED; otherwise UNKNOWN.
- Inventory: UNKNOWN because raw OOS counts have no approved materiality threshold.
- Overall: Sales/CM precedence only; Ads and Inventory do not override.
- Data Confidence: evaluated independently from Business Health.

The former Phase 2B proposal remains inactive as historical evidence. The active contract is
`config/business_health_rules_v1.yaml`.

## 3. Current Walmart rule evaluation

| Output | Result | Deterministic reason |
|---|---|---|
| Sales Health | RED | Actual Sales -694.21 is below zero |
| CM Health | RED | Actual CM -3,273.32 is below zero |
| Ads Health | RED | Ad Spend 221.63 is positive and Attributed Sales is zero |
| Inventory Health | UNKNOWN | No approved Walmart inventory threshold |
| Overall Health | RED | Sales or CM RED forces Overall RED |

The engine produced the expected results without hardcoding the outputs.

## 4. Data Confidence

Result: `MEDIUM`.

Sales, CM and BP evidence is authoritative, available, CURRENT and reconciled. Confidence is not
HIGH because there are non-blocking limitations: Sales/Ads/Inventory are through 2026-08-02 while
CM is through 2026-08-10, YTD CM is optional and unavailable, Inventory Health remains unresolved,
and one superseded/unregistered weekly history row was correctly excluded. None of these limitations
converts Business Health to RED or YELLOW.

## 5. Cockpit Preview v3

The preview is generated at
`data/cockpit/phase2c/walmart_cockpit_preview_v3.md`. It preserves `control_week=2026-W33`, native
periods, source-specific data-through dates, the official -694.21 net-sales semantics and the exact
comparable weekly change of -78.82%.

Management interpretation remains bounded:

- Primary Driver uses the deterministic Sales RED reason.
- Key Risk, Key Opportunity and Required Action remain UNRESOLVED.
- No Signal, Action or recommendation was generated.

## 6. Live-write candidate

The complete candidate is
`data/cockpit/phase2c/walmart_feishu_live_write_candidate.json`.

- Identity / upsert key: `Health ID = HLT-2026W33-US-WMT`
- Target: `STORM | Business Control` / `01 Business Health`
- Expected behavior: create if no match; update machine-owned fields if exactly one match; abort on
  duplicate identities.
- Update payload excludes Human Reviewed, Snapshot Locked and human/system-managed fields so a later
  supervised update cannot silently overwrite governance state.
- Record API invoked: `false`
- External record write performed: `false`
- Validation basis: `LOCAL_APPROVED_DELTA_OVERLAY_PENDING_LIVE_SCHEMA`

## 7. Feishu mapping review

The candidate maps 20 fields, including the approved `CM Health` and `Data Confidence` controls.
Twelve control inputs remain intentionally without dedicated numeric Feishu fields:

`actual_sales`, `bp_sales`, `sales_attainment_pct`, `actual_cm`, `bp_cm`, `cm_attainment_pct`,
`actual_cm_pct`, `ad_spend`, `attributed_ad_sales`, `roas`, `inventory_condition`, and
`weekly_sales_change`.

They drive deterministic controls or concise evidence but do not expand the management schema.
`inventory_units` and `ytd_actual_cm` remain diagnostic only. Primary Driver has no dedicated Feishu
field. Unsupported domain health fields and manual management fields are intentionally omitted.

## 8. Validation

- Focused Phase 2C rules/mapping/no-write tests: passed.
- Full project suite: `77 passed`.
- Preview and candidate are generated from official Walmart run `20260804_151643_WEEKLY` and accepted
  Structured Metrics batch `5a7ee7c5-4895-4243-b771-39143bc42011`.
- No record create/update method was called.

## 9. Modified files

- `config/business_health_rules_v1.yaml`
- `config/cockpit_metrics.yaml`
- `src/storm/cockpit/models.py`
- `src/storm/cockpit/rules.py`
- `src/storm/cockpit/feishu_dry_run.py`
- `src/storm/cockpit/__init__.py`
- `scripts/build_phase2c_walmart_control_plane.py`
- `tests/test_phase2c_control_plane.py`
- `tests/test_cockpit_metric_contract.py`
- `docs/phase2c_control_plane_activation.md`

Generated artifacts are under `data/cockpit/phase2c/` and are excluded from the tracked source tree.

## 10. Blocker and stop gate

Blocker: `FEISHU_RUNTIME_BASE_TOKEN_REQUIRED`.

To resume, make the approved Base token available only at runtime in a new/resumed task. The next
operation must be: list the four tables, list all fields in `01 Business Health`, reconcile exactly
against the current manifest, create only the two missing approved fields, reread the schema, update
the manifest with verified field IDs/counts, rebuild the candidate with live validation, and STOP
again before any record create/update call.
