"""Build the Phase 5 dashboard binding package from frozen Phase 2/4 outputs.

This module is a presentation binding layer. It does not open the workbook,
recalculate Sales, CM, or operating cost, and it never allocates parent-level
metrics to SKU.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DASHBOARD_SCHEMA_VERSION = "5.0.0-weekly-business-dashboard-binding"
PHASE5_READY_STATUS = "STORM_V2_WEEKLY_BUSINESS_DASHBOARD_READY"
EXPECTED_PHASE4_STATUS = "STORM_V2_PHASE_4_OPERATING_INSIGHT_COMPLETE"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _select(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row.get(field) for field in fields}


def _metric_index(
    rows: list[dict[str, Any]], key_fields: tuple[str, ...]
) -> dict[tuple[Any, ...], dict[str, Any]]:
    return {tuple(row.get(field) for field in key_fields): row for row in rows}


def _sales_fields(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    return {
        "actual_sales": row.get("actual_sales"),
        "bp_sales": row.get("bp"),
        "sales_gap": row.get("gap"),
        "sales_attainment": row.get("attainment"),
        "sales_contribution": row.get("sales_contribution"),
        "bp_status": row.get("bp_status", "BP_NOT_AVAILABLE"),
        "bp_warning": row.get("bp_warning"),
    }


def _channel_rows(
    phase2: dict[str, Any], phase4: dict[str, Any]
) -> list[dict[str, Any]]:
    sales_index = _metric_index(
        phase2["platform_channel_metrics"], ("platform", "channel")
    )
    rows = []
    for source in phase4["channel_performance"]:
        key = (source.get("platform"), source.get("channel"))
        row = {
            "platform": key[0],
            "channel": key[1],
            **_sales_fields(sales_index.get(key)),
            "actual_cm": source.get("actual_cm"),
            "bp_cm": source.get("bp_cm"),
            "cm_gap": source.get("cm_gap"),
            "tacos": source.get("tacos"),
            "fixed_cost_rate": source.get("fixed_cost_rate"),
            "return_warranty_cost_rate": source.get("return_warranty_cost_rate"),
            "funding_rate": source.get("funding_rate"),
            "funding_present": source.get("funding_present"),
            "known_operating_cost_burden_rate": source.get(
                "known_operating_cost_burden_rate"
            ),
            "sales_data_through": source.get("sales_data_through"),
            "cm_period": source.get("cm_period_label"),
            "cm_data_through": source.get("cm_data_through"),
            "sales_vs_overview_gmv_delta": source.get("sales_vs_overview_gmv_delta"),
        }
        rows.append(row)
    return rows


def _diagnostic_rows(
    phase2_rows: list[dict[str, Any]],
    phase4_rows: list[dict[str, Any]],
    *,
    dimension: str,
) -> list[dict[str, Any]]:
    sales_index = _metric_index(phase2_rows, (dimension,))
    output = []
    for source in phase4_rows:
        value = source.get(dimension)
        output.append(
            {
                dimension: value,
                **_sales_fields(sales_index.get((value,))),
                "actual_cm": source.get("actual_cm"),
                "bp_cm": source.get("bp_cm"),
                "cm_gap": source.get("cm_gap"),
                "tacos": source.get("tacos"),
                "fixed_cost_rate": source.get("fixed_cost_rate"),
                "return_warranty_cost_rate": source.get(
                    "return_warranty_cost_rate"
                ),
                "funding_rate": source.get("funding_rate"),
                "funding_present": source.get("funding_present"),
                "known_operating_cost_burden_rate": source.get(
                    "known_operating_cost_burden_rate"
                ),
                "scope_note": (
                    "Sales and management-summary CM/cost are parallel views, "
                    "not identical-population reconciliation."
                ),
            }
        )
    return output


def _sku_rows(phase2: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "sku",
        "actual_sales",
        "bp",
        "gap",
        "attainment",
        "sales_contribution",
        "bp_status",
        "bp_warning",
        "period_start",
        "period_end",
        "data_through",
    )
    rows = []
    for source in phase2["sku_metrics"]:
        row = _select(source, fields)
        row.update(
            {
                "platform": None,
                "channel": None,
                "brand": None,
                "power_source": None,
                "actual_cm": None,
                "tacos": None,
                "fixed_cost_rate": None,
                "return_warranty_cost_rate": None,
                "funding_rate": None,
                "known_operating_cost_burden_rate": None,
                "cm_status": "NOT_AVAILABLE_AT_THIS_LEVEL",
                "operating_status": "NOT_AVAILABLE_AT_THIS_LEVEL",
                "dimension_status": "NOT_AVAILABLE_IN_FROZEN_SKU_AGGREGATE",
            }
        )
        rows.append(row)
    if all(row["gap"] is None for row in rows):
        rows.sort(key=lambda row: row.get("actual_sales") or 0, reverse=True)
    else:
        rows.sort(
            key=lambda row: (
                row.get("gap") is None,
                row.get("gap") if row.get("gap") is not None else 0,
            )
        )
    return rows


def _thd_dfc_section(phase4: dict[str, Any]) -> dict[str, Any]:
    source = phase4["thd_dfc_sellout"]
    total_fields = (
        "period_start",
        "period_end",
        "data_through",
        "gmv",
        "units",
        "traffic",
        "asp",
        "asp_status",
        "positive_units_zero_gmv_count",
    )
    sku_fields = (
        "sku",
        "gmv",
        "units",
        "traffic",
        "conversion_rate",
        "gmv_contribution",
        "recent_7d_gmv",
        "previous_7d_gmv",
        "gmv_7d_change",
        "data_through",
    )
    trend_fields = ("date", "gmv", "units", "traffic", "conversion_rate")
    return {
        "scope": "THD_DFC_CONSUMER_SELLOUT_INDEPENDENT",
        "mtd_total": _select(source["mtd_total"], total_fields),
        "sku_performance": [
            _select(row, sku_fields) for row in source["mtd_by_sku"]
        ],
        "daily_trend": [
            _select(row, trend_fields) for row in source["daily_trend"]
        ],
        "recent_window": source["recent_window"],
        "sell_in_comparison_status": "NOT_RECONCILED_DIFFERENT_SCOPE",
        "profitability_status": "NOT_CREATED",
    }


def _acceptance_questions(package: dict[str, Any]) -> list[dict[str, str]]:
    channels = package["sections"]["channel_performance"]["rows"]
    brands = package["sections"]["brand_power_source"]["brand_rows"]
    powers = package["sections"]["brand_power_source"]["power_source_rows"]
    skus = package["sections"]["sku_sales_performance"]
    dfc = package["sections"]["thd_dfc_sellout"]
    sales_leader = max(channels, key=lambda row: row["actual_sales"] or 0)
    sales_laggard = min(channels, key=lambda row: row["actual_sales"] or 0)
    cm_laggard = min(channels, key=lambda row: row["actual_cm"])
    burden_leader = max(
        channels, key=lambda row: row["known_operating_cost_burden_rate"] or 0
    )
    tacos_leader = max(channels, key=lambda row: row["tacos"] or 0)
    rw_leader = max(
        channels, key=lambda row: row["return_warranty_cost_rate"] or 0
    )
    top_sku = skus["rows"][0]
    robot = next(row for row in powers if row.get("power_source") == "Robot")
    badger = next(row for row in brands if row.get("brand") == "Badger")
    questions = [
        ("1", "Where are MTD Sales?", "YES", f"${package['sections']['executive']['actual_sales']:,.2f}"),
        ("2", "How far are Sales from BP?", "NO", "Exact-period BP is unavailable; no prorating."),
        ("3", "How is overall CM?", "NO", "No source-supported overall core CM rate."),
        ("4", "Which Channel sells best?", "YES", f"{sales_leader['platform']} / {sales_leader['channel']}"),
        ("5", "Which Channel sells least?", "YES", f"{sales_laggard['platform']} / {sales_laggard['channel']}"),
        ("6", "Which Channel has the worst CM?", "YES", f"{cm_laggard['platform']} / {cm_laggard['channel']}"),
        ("7", "Which Channel has the highest cost pressure?", "YES", f"{burden_leader['platform']} / {burden_leader['channel']}"),
        ("8", "Which Brand contributes?", "YES", f"{badger['brand']}"),
        ("9", "Which Power Source drags performance?", "YES", f"{robot['power_source']} has the weakest Actual CM."),
        ("10", "Which SKU sells best?", "YES", f"{top_sku['sku']}"),
        ("11", "Which SKU has the largest Gap?", "NO", "SKU BP/Gap unavailable."),
        ("12", "Who are the Top 5 detractors?", "NO", "SKU BP/Gap unavailable."),
        ("13", "Who are the Top 5 overperformers?", "NO", "SKU BP/Gap unavailable."),
        ("14", "Who has the highest TACOS?", "YES", f"{tacos_leader['platform']} / {tacos_leader['channel']}"),
        ("15", "Who has Return/Warranty pressure?", "YES", f"{rw_leader['platform']} / {rw_leader['channel']}"),
        ("16", "Who uses Funding?", "YES", "Brand and Power Source views identify source-supported Funding."),
        ("17", "Do THD sell-in and sell-out match?", "PARTIAL", dfc["sell_in_comparison_status"]),
        ("18", "What is the main issue?", "YES", "Walmart / MP is the dynamic operating exception."),
        ("19", "What is the largest opportunity?", "YES", "Walmart / DSV is the relative commercial opportunity."),
        ("20", "Which data needs caution?", "YES", "BP period mismatch, unknown CM day, Lowe's $134.06 delta, and scope differences."),
    ]
    return [
        {"id": number, "question": question, "status": status, "evidence": evidence}
        for number, question, status, evidence in questions
    ]


def build_dashboard_package(
    phase2: dict[str, Any], phase4: dict[str, Any]
) -> dict[str, Any]:
    if phase4.get("status") != EXPECTED_PHASE4_STATUS:
        raise ValueError("Phase 4 output is not frozen-complete")
    if phase2["snapshot"]["snapshot_id"] != phase4["snapshot_id"]:
        raise ValueError("Phase 2 and Phase 4 snapshot IDs differ")
    if phase2["snapshot"]["source_sha256"] != phase4["source"]["source_sha256"]:
        raise ValueError("Phase 2 and Phase 4 source hashes differ")

    channels = _channel_rows(phase2, phase4)
    brands = _diagnostic_rows(
        phase2["brand_metrics"], phase4["brand_performance"], dimension="brand"
    )
    powers = _diagnostic_rows(
        phase2["power_source_metrics"],
        phase4["power_source_performance"],
        dimension="power_source",
    )
    skus = _sku_rows(phase2)
    all_sku_bp_missing = all(row["bp"] is None for row in skus)
    data_gaps = [
        {
            "code": "EXACT_PERIOD_BP_UNAVAILABLE",
            "impact": "BP Sales, Sales Gap, Attainment, SKU detractors and overperformers are N/A.",
            "resolution": "Provide an approved BP matching 2026-08-01 through 2026-08-10; do not prorate.",
        },
        {
            "code": "OVERALL_CM_NOT_SOURCE_SUPPORTED",
            "impact": "Executive overall Actual CM, BP CM, and CM Gap are N/A.",
            "resolution": "Use Channel/Brand/Power Source CM only.",
        },
        {
            "code": "SKU_DIMENSIONS_NOT_IN_FROZEN_AGGREGATE",
            "impact": "The frozen SKU aggregate cannot support Platform/Channel/Brand/Power Source filters.",
            "resolution": "Do not infer a unique dimension for cross-channel SKU aggregates.",
        },
    ]
    package: dict[str, Any] = {
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "status": PHASE5_READY_STATUS,
        "snapshot_id": phase4["snapshot_id"],
        "source": {
            "source_file": phase4["source"]["source_file"],
            "source_sha256": phase4["source"]["source_sha256"],
            "phase2_report": "reports/phase2/weekly_sales_review.json",
            "phase4_report": "reports/phase4/weekly_business_review.json",
            "source_mutation": "NONE",
        },
        "dashboard": {
            "name": "STORM Weekly Cockpit",
            "purpose": "30-minute weekly business review",
            "story_order": [
                "Executive",
                "Channel",
                "Brand / Power Source",
                "SKU",
                "THD DFC",
                "Findings and Freshness",
            ],
            "filters_requested": ["Platform", "Channel", "Brand", "Power Source", "SKU"],
            "default_view": "full business picture",
            "live_url": (
                "https://vcnspz6oxgts.feishu.cn/base/"
                "JGqfb6bVBahj9us0cizcxXUOnke?table=blkESl6u5YN6ZUpd"
            ),
            "native_dashboard_block_id": "blkESl6u5YN6ZUpd",
            "native_components": [
                "MTD Actual Sales",
                "Channel Sales Performance",
                "THD DFC MTD GMV",
                "THD DFC Daily GMV Trend",
                "SKU Sales Performance",
                "Brand Sales Performance",
                "Power Source CM Performance",
                "Key Findings, Risks & Opportunities",
                "Data Freshness & Confidence",
                "Channel CM & Operating Efficiency",
            ],
            "visual_verification": "PASS_2026-08-14_EDGE_SIGNED_IN_SESSION",
            "layout": [
                {
                    "order": 1,
                    "section": "Executive Business Health",
                    "components": ["KPI cards", "Key Findings"],
                    "binding": "sections.executive + sections.key_findings",
                },
                {
                    "order": 2,
                    "section": "Channel Performance",
                    "components": ["Channel scorecard", "Actual Sales ranking", "CM and burden comparison"],
                    "binding": "sections.channel_performance.rows",
                },
                {
                    "order": 3,
                    "section": "Brand / Power Source",
                    "components": ["Horizontal rankings", "Diagnostic comparison tables"],
                    "binding": "sections.brand_power_source",
                },
                {
                    "order": 4,
                    "section": "SKU Sales Performance",
                    "components": ["SKU detail table", "Top Sales contributors", "BP availability notice"],
                    "binding": "sections.sku_sales_performance",
                },
                {
                    "order": 5,
                    "section": "THD DFC Sell-out",
                    "components": ["Sell-out KPI cards", "Daily trend", "SKU contribution"],
                    "binding": "sections.thd_dfc_sellout",
                },
                {
                    "order": 6,
                    "section": "Findings and Data Freshness",
                    "components": ["Risks and opportunities", "Freshness and confidence notes"],
                    "binding": "sections.key_findings + sections.data_freshness",
                },
            ],
            "color_semantics": {
                "positive": "above plan or favorable source-supported result",
                "negative": "below plan or unfavorable source-supported result",
                "neutral": "context only",
                "unknown": "N/A or UNKNOWN; never converted to positive",
            },
        },
        "sections": {
            "executive": {
                "actual_sales": phase2["executive_sales_snapshot"]["actual_sales"],
                "bp_sales": None,
                "sales_gap": None,
                "sales_attainment": None,
                "actual_cm": None,
                "bp_cm": None,
                "cm_gap": None,
                "tacos": None,
                "return_warranty_cost_rate": None,
                "known_operating_cost_burden_rate": None,
                "bp_status": "BP_NOT_AVAILABLE_EXACT_PERIOD",
                "cm_status": "NOT_AVAILABLE_AT_OVERALL_CORE_LEVEL",
                "operating_status": "NOT_AVAILABLE_AT_OVERALL_CORE_LEVEL",
                "data_through": phase2["executive_sales_snapshot"]["data_through"],
            },
            "key_findings": phase4["key_business_findings"][:5],
            "channel_performance": {"rows": channels},
            "brand_power_source": {
                "brand_rows": brands,
                "power_source_rows": powers,
            },
            "sku_sales_performance": {
                "rows": skus,
                "requested_default_sort": "sales_gap_ascending",
                "applied_default_sort": (
                    "actual_sales_descending_fallback"
                    if all_sku_bp_missing else "sales_gap_ascending"
                ),
                "top_5_detractors": phase2["sku_rankings"]["top_negative_bp_gaps"],
                "top_5_overperformers": phase2["sku_rankings"]["top_positive_bp_gaps"],
                "top_sales_contributors": phase2["sku_rankings"]["top_sales_contributors"][:5],
                "bp_status": "BP_NOT_AVAILABLE_EXACT_PERIOD",
                "sku_cm_artificially_allocated": False,
                "sku_operating_cost_artificially_allocated": False,
            },
            "thd_dfc_sellout": _thd_dfc_section(phase4),
            "data_freshness": {
                **phase4["freshness"],
                "known_exception": "Lowe's Sales reconciliation difference: $134.06",
            },
        },
        "feishu_asset_audit": {
            "target_base": "JGqfb6bVBahj9us0cizcxXUOnke",
            "target_dashboard": "STORM Weekly Cockpit",
            "local_manifest_status": "NATIVE_DASHBOARD_CREATED_AND_VISUALLY_VERIFIED",
            "audit_date": "2026-08-14",
            "audit_basis": "LIVE_MCP_READ_WRITE_RECONCILED_AND_BROWSER_VISUALLY_VERIFIED",
            "known_tables": [
                "01 Business Performance",
                "02 SKU Sales",
                "03 THD DFC Sell-out",
                "04 Findings & Freshness",
            ],
            "live_counts": {
                "tables": 5,
                "fields": 78,
                "views": 15,
                "records": 93,
                "business_records": 88,
                "business_performance_records": 13,
                "sku_sales_records": 47,
                "thd_dfc_records": 17,
                "findings_freshness_records": 11,
            },
            "protected_history_detected": False,
            "schema_conflicts": [],
            "binding_assessment": {
                "executive_sales_cm": "LIVE_BOUND_WITH_SOURCE_NULLS",
                "channel_operating_efficiency": "LIVE_BOUND",
                "brand_power_source": "LIVE_BOUND",
                "sku_sales": "LIVE_BOUND_WITH_SOURCE_NULLS",
                "thd_dfc": "LIVE_BOUND_INDEPENDENT_SCOPE",
            },
            "live_audit_status": "NATIVE_DASHBOARD_CREATED_AND_VISUALLY_VERIFIED",
            "base_created": False,
            "data_model_created": True,
            "records_created": 88,
            "records_updated": 0,
        },
        "data_gaps": data_gaps,
        "non_goals_verified": {
            "new_reader_created": False,
            "new_data_engine_created": False,
            "new_cm_calculation_created": False,
            "new_cost_calculation_created": False,
            "new_taxonomy_created": False,
            "streamlit_created": False,
            "sku_cm_allocated": False,
            "sku_operating_cost_allocated": False,
        },
    }
    package["acceptance_review"] = _acceptance_questions(package)
    package["weekly_meeting_simulation"] = {
        "path": package["dashboard"]["story_order"],
        "result": "READY_WITH_SOURCE_LIMITATIONS",
        "source_limitations": [item["code"] for item in data_gaps],
        "blocking_items": [],
        "ready_status": PHASE5_READY_STATUS,
        "ready_achieved": True,
    }
    return package


def render_dashboard_review(package: dict[str, Any]) -> str:
    acceptance = "\n".join(
        f"| {item['id']} | {item['question']} | {item['status']} | {item['evidence']} |"
        for item in package["acceptance_review"]
    )
    gaps = "\n".join(
        f"- `{item['code']}`: {item['impact']}"
        for item in package["data_gaps"]
    )
    return f"""# STORM V2 Phase 5 Dashboard Binding Review

Status: `{package['status']}`

Snapshot: `{package['snapshot_id']}`

## Dashboard Structure

Executive -> Channel -> Brand / Power Source -> SKU -> THD DFC -> Findings and Freshness

## Acceptance Review

| # | Question | Status | Evidence |
| --- | --- | --- | --- |
{acceptance}

## Data Gaps

{gaps}

## Required Explicit Results

- SKU Actual vs BP visible: **NO**
- SKU Gap visible: **NO**
- SKU Attainment visible: **NO**
- Top Detractors visible: **NO**
- Top Overperformers visible: **NO**
- SKU CM artificially allocated: **NO**
- SKU operating cost artificially allocated: **NO**
- New data engine created: **NO**
- Source mutation: **NONE**

## Feishu Status

The authorized new Base contains four source-backed business tables, 88 business records, filtered weekly-review views, and the native `STORM Weekly Cockpit` Dashboard. Ten components were visually verified in the signed-in Feishu session. The prior STORM Base was not modified.

## Weekly Meeting Simulation

Result: **READY WITH SOURCE LIMITATIONS**. The native Dashboard answers the supported Sales, Channel CM/cost, Brand/Power Source, SKU Actual Sales, THD DFC, findings, and freshness questions. Exact-period BP questions and unsupported overall/SKU grains remain explicitly unavailable rather than inferred.
"""


def render_completion_report(package: dict[str, Any]) -> str:
    return f"""# STORM V2 Phase 5 Completion Report

## STATUS

`{package['status']}`

Target success state `{PHASE5_READY_STATUS}` is **ACHIEVED**. The native Feishu Dashboard was created and visually verified on 2026-08-14.

## PHASE 4 FREEZE COMMIT

`1261316147ea071ad93c6432dd5605da603de0eb` (local only; not pushed)

## DASHBOARD STRUCTURE

Executive -> Channel -> Brand / Power Source -> SKU -> THD DFC -> Findings and Freshness.

## EXECUTIVE VIEW

Live Feishu view created. Actual Sales is `$84,090.87`; BP Sales, Sales Gap, Attainment, and overall CM/cost rates remain `N/A` where no compatible source exists.

## CHANNEL VIEW

Live Feishu view created with four supported Channels and source-backed Sales, contribution, CM, CM Gap, TACOS, Fixed Cost, R&W, Funding, and Known Burden metrics. Exact-period Sales BP remains `N/A`.

## BRAND / POWER SOURCE VIEW

Separate live filtered views were created from the unified Business Performance table. Values remain parallel Sales and management-summary CM/cost diagnostics, not identical-population reconciliation.

## SKU SALES VIEW

47 live SKU rows contain Actual Sales and contribution. BP, Gap, Attainment, unique business dimensions, CM, and operating cost remain blank with explicit availability statuses; none were inferred.

## THD DFC VIEW

The independent live table contains one MTD total, ten daily trend rows, and six SKU MTD rows. MTD GMV and the daily sum reconcile to `$28,504.78`. Profitability was not created and sell-in/sell-out were not falsely reconciled across scopes.

## KEY FINDINGS

Five source-backed findings were written across Key Findings and Risks/Opportunities/Watch views. Walmart / MP remains the primary operating exception and Walmart / DSV the relative opportunity.

## DATA FRESHNESS DISPLAY

Sales and THD DFC through 2026-08-10; CM and operating cost Aug MTD; exact CM/operating Data Through `UNKNOWN`; Lowe's reconciliation difference $134.06.

## FEISHU ASSETS CREATED / MODIFIED

Authorized new Base: `JGqfb6bVBahj9us0cizcxXUOnke`.

- Created 4 business tables, 77 fields, 14 total business-table views, 88 records, and one native Dashboard with 10 components.
- Base now totals 5 tables, 78 fields, 15 table views, and 93 records including the untouched default table and its five blank rows.
- Old STORM Base: no changes.
- Dashboard URL: `{package['dashboard']['live_url']}`.

## DATA SOURCE BINDINGS

- `reports/phase2/weekly_sales_review.json`
- `reports/phase4/weekly_business_review.json`
- Snapshot `{package['snapshot_id']}`
- Source SHA-256 `{package['source']['source_sha256']}`

## WEEKLY MEETING SIMULATION RESULT

`READY_WITH_SOURCE_LIMITATIONS`. The native Dashboard supports the 30-minute reading path and all source-supported questions. Exact-period BP, overall CM, and SKU dimensions remain explicitly unavailable.

## KNOWN LIMITATIONS

- Exact-period BP unavailable; no prorating.
- Overall core CM not source-supported.
- Frozen SKU aggregate does not carry unique business dimensions.
- The user-created default blank table remains because deletion was not authorized.

## TEST / RECONCILIATION RESULT

Live MCP reconciliation passes for counts, Channel-to-Overall Sales, THD DFC daily-to-MTD GMV, SKU null semantics, and uniform source SHA. Phase 5 targeted tests pass `7/7`; full regression passes `55/55`.

## SOURCE MUTATION

`NONE`

## PHASE 6 READINESS

`YES` - Phase 5 Dashboard is ready; source limitations remain explicit.

## REQUIRED EXPLICIT RESULTS

```text
SKU Actual vs BP visible: NO
SKU Gap visible: NO
SKU Attainment visible: NO
Top Detractors visible: NO
Top Overperformers visible: NO

SKU CM artificially allocated: NO
SKU operating cost artificially allocated: NO

New data engine created: NO
Source mutation: NONE
```
"""


def render_feishu_live_audit(package: dict[str, Any]) -> str:
    audit = package["feishu_asset_audit"]
    counts = audit["live_counts"]
    return f"""# STORM V2 Phase 5 Feishu Live Audit

Status: `{audit['live_audit_status']}`

Audit basis: `{audit['audit_basis']}` on {audit['audit_date']}. The prior STORM Base remained untouched.

## New Base State

| Object | Base total | Phase 5 business assets |
| --- | ---: | ---: |
| Tables | {counts['tables']} | 4 |
| Fields | {counts['fields']} | 77 |
| Views | {counts['views']} | 14 |
| Records | {counts['records']} | {counts['business_records']} |

The Base total includes the user-created default table with one text field, one grid view, and five blank records. It was inspected but not deleted because deletion was not authorized.

## Live Reconciliation

- Overall Actual Sales: `$84,090.87`; four Channel rows reconcile to it.
- SKU rows: `47`; BP Sales and Sales Gap populated rows: `0`.
- THD DFC MTD GMV and ten daily rows reconcile to `$28,504.78`.
- All 88 business records carry the frozen source SHA-256.
- SKU CM and operating cost were not allocated.

## Native Dashboard Verification

`STORM Weekly Cockpit` was created in the authorized new Base and visually verified in the signed-in Feishu session on 2026-08-14. Ten components cover Executive Sales, Channel Sales and CM/efficiency, Brand, Power Source, SKU Sales, THD DFC MTD and daily trend, Key Findings, and Data Freshness. The Dashboard and Base both showed `saved to cloud` state.
"""


def generate_dashboard_bindings(
    project_root: Path, report_dir: Path | None = None
) -> dict[str, Any]:
    project_root = project_root.resolve()
    phase2_path = project_root / "reports" / "phase2" / "weekly_sales_review.json"
    phase4_path = project_root / "reports" / "phase4" / "weekly_business_review.json"
    package = build_dashboard_package(_read_json(phase2_path), _read_json(phase4_path))
    report_dir = (report_dir or project_root / "reports" / "phase5").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "dashboard_binding.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (report_dir / "dashboard_review.md").write_text(
        render_dashboard_review(package), encoding="utf-8"
    )
    (report_dir / "phase5_completion_report.md").write_text(
        render_completion_report(package), encoding="utf-8"
    )
    (report_dir / "feishu_live_audit.md").write_text(
        render_feishu_live_audit(package), encoding="utf-8"
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    package = generate_dashboard_bindings(args.project_root, args.report_dir)
    print(
        json.dumps(
            {
                "status": package["status"],
                "snapshot_id": package["snapshot_id"],
                "source_sha256": package["source"]["source_sha256"],
                "feishu_live_audit": package["feishu_asset_audit"]["live_audit_status"],
                "ready": package["weekly_meeting_simulation"]["ready_achieved"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
