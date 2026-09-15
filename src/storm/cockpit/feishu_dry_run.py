"""Map a cockpit snapshot to existing Feishu fields without any external write."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from storm.domain.ids import mint_health_id

from .models import BusinessHealthSnapshot


class FeishuMappingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FeishuDryRun:
    mode: str
    target_table: str
    external_write_performed: bool
    record: dict[str, Any]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "target_table": self.target_table, "external_write_performed": self.external_write_performed, "record": self.record, "diagnostics": self.diagnostics}


@dataclass(frozen=True, slots=True)
class FeishuWriteCandidate:
    mode: str
    target: dict[str, Any]
    identity: dict[str, Any]
    create_fields: dict[str, Any]
    update_fields: dict[str, Any]
    omitted_fields: dict[str, str]
    source_snapshot_ids: dict[str, Any]
    data_through_dates: dict[str, Any]
    mapping_review: dict[str, Any]
    validation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "target": self.target,
            "identity": self.identity,
            "create_fields": self.create_fields,
            "update_fields": self.update_fields,
            "omitted_fields": self.omitted_fields,
            "source_snapshot_ids": self.source_snapshot_ids,
            "data_through_dates": self.data_through_dates,
            "mapping_review": self.mapping_review,
            "validation": self.validation,
        }


def _number(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "NULL"
    return f"{float(value):.2%}" if percent else f"{float(value):,.2f}"


def build_feishu_dry_run(snapshot: BusinessHealthSnapshot, schema_path: str | Path) -> FeishuDryRun:
    schema = yaml.safe_load(Path(schema_path).read_text(encoding="utf-8"))
    table = next(item for item in schema["tables"] if item["name"] == "01 Business Health")
    allowed_fields = {item["name"] for item in table["fields"]}
    facts = snapshot.facts
    derived = snapshot.derived_control_metrics
    trend = derived["weekly_sales_change"].value
    top_change = "UNRESOLVED — comparable weekly evidence unavailable."
    if trend is not None:
        top_change = (
            f"Equal-length weekly net sales changed {_number(trend['percent_change'], percent=True)} "
            f"({_number(trend['absolute_change'])} USD): {trend['previous_period_start']}–{trend['previous_period_end']} "
            f"vs {trend['current_period_start']}–{trend['current_period_end']}."
        )
    sales_cutoff = snapshot.data_status["sales"].data_through_date
    cm_cutoff = snapshot.data_status["cm_actual"].data_through_date
    weekly_summary = (
        f"Walmart net sales {_number(facts['actual_sales'].value)} USD through {sales_cutoff}; "
        f"full-month BP sales {_number(facts['bp_sales'].value)} USD; progress {_number(derived['sales_attainment_pct'].value, percent=True)}. "
        f"Actual CM {_number(facts['actual_cm'].value)} USD through {cm_cutoff}; full-month BP CM {_number(facts['bp_cm'].value)} USD; "
        f"CM progress {_number(derived['cm_attainment_pct'].value, percent=True)}; CM% {_number(derived['actual_cm_pct'].value, percent=True)}. "
        f"Ad spend {_number(facts['ad_spend'].value)} USD; attributed sales {_number(facts['attributed_ad_sales'].value)} USD; "
        f"ROAS {_number(facts['roas'].value)}. Cutoffs are native and not treated as a common comparison date."
    )
    record = {
        "Health ID": mint_health_id(snapshot.control_week, snapshot.market, "WMT"),
        "Week": snapshot.control_week, "Market": snapshot.market, "Platform": "Walmart",
        "Level": snapshot.level, "Channel": None, "Overall Health": "UNKNOWN",
        "Sales Health": "UNKNOWN", "CM Health": "UNKNOWN",
        "Ads Health": "UNKNOWN", "Inventory Health": "UNKNOWN",
        "Buyability Health": "UNKNOWN", "Weekly Summary": weekly_summary, "Top Change": top_change,
        "Top Risk": "UNRESOLVED", "Top Opportunity": "UNRESOLVED",
        "Next Priority": "UNRESOLVED — human review required.", "Data Completeness": "PARTIAL",
        "Data Confidence": "UNKNOWN",
        "Data As Of": None, "Source Type": "MIXED",
        "Source Ref": f"Walmart run {facts['actual_sales'].source_release}; STORM batch {facts['actual_cm'].import_batch_id}",
        "Human Reviewed": False, "Snapshot Locked": False,
    }
    extra = set(record) - allowed_fields
    if extra:
        raise FeishuMappingError(f"UNKNOWN_FEISHU_FIELDS: {sorted(extra)}")
    required = {item["name"] for item in table["fields"] if item.get("required")}
    missing = {name for name in required if name not in record or record[name] is None}
    if missing:
        raise FeishuMappingError(f"REQUIRED_FEISHU_FIELDS_MISSING: {sorted(missing)}")
    unmapped = [
        {"metric": name, "reason": "NO_DEDICATED_STRUCTURED_FIELD_IN_01_BUSINESS_HEALTH; retained in structured snapshot; narrative fields are display-only"}
        for name in (
            "actual_sales", "bp_sales", "sales_attainment_pct", "actual_cm", "bp_cm",
            "cm_attainment_pct", "actual_cm_pct", "ad_spend", "attributed_ad_sales", "roas",
            "inventory_units", "inventory_condition", "weekly_sales_change", "ytd_actual_cm",
        )
    ]
    diagnostics = {
        "schema_change_performed": False, "live_lookup_performed": False,
        "mixed_native_cutoffs": True,
        "data_as_of_omitted_reason": f"NO_SINGLE_TRUTHFUL_DATE: sales through {sales_cutoff}; CM through {cm_cutoff}",
        "health_rule_status": "UNRESOLVED_NO_APPROVED_THRESHOLDS",
        "source_warnings": list(snapshot.warnings), "unmapped_metrics": unmapped,
    }
    return FeishuDryRun("DRY_RUN", "01 Business Health", False, record, diagnostics)


def render_preview(snapshot: BusinessHealthSnapshot, dry_run: FeishuDryRun) -> str:
    facts = snapshot.facts
    derived = snapshot.derived_control_metrics
    return "\n".join([
        "# STORM Phase 2A — Walmart Business Health Preview", "",
        f"- Grain: `{snapshot.control_week} × {snapshot.market} × {snapshot.platform} × {snapshot.level}`",
        f"- Snapshot date: `{snapshot.snapshot_date}`",
        "- Mode: `DRY_RUN`; no Feishu write, schema change, signal, or action was performed.", "",
        "## Facts", "", "| Metric | Value | Native cutoff | Source |", "|---|---:|---|---|",
        f"| Actual Sales | {_number(facts['actual_sales'].value)} USD | {facts['actual_sales'].data_through_date} | Walmart official MTD |",
        f"| BP Sales | {_number(facts['bp_sales'].value)} USD | Full month {facts['bp_sales'].period_end} | Structured Metrics |",
        f"| Sales Attainment | {_number(derived['sales_attainment_pct'].value, percent=True)} | {derived['sales_attainment_pct'].comparison_through_date} | MTD vs full-month target |",
        f"| Actual CM | {_number(facts['actual_cm'].value)} USD | {facts['actual_cm'].data_through_date} | Structured Metrics |",
        f"| BP CM | {_number(facts['bp_cm'].value)} USD | Full month {facts['bp_cm'].period_end} | Structured Metrics |",
        f"| CM Attainment | {_number(derived['cm_attainment_pct'].value, percent=True)} | {derived['cm_attainment_pct'].comparison_through_date} | MTD vs full-month target |",
        f"| CM % | {_number(derived['actual_cm_pct'].value, percent=True)} | {derived['actual_cm_pct'].comparison_through_date} | Same CM batch |",
        f"| Ad Spend | {_number(facts['ad_spend'].value)} USD | {facts['ad_spend'].data_through_date} | Walmart official MTD |",
        f"| Attributed Ad Sales | {_number(facts['attributed_ad_sales'].value)} USD | {facts['attributed_ad_sales'].data_through_date} | Walmart official MTD |",
        f"| ROAS | {_number(facts['roas'].value)} | {facts['roas'].data_through_date} | Walmart official MTD |",
        f"| Inventory Units | {_number(facts['inventory_units'].value)} | {facts['inventory_units'].data_through_date} | Walmart official snapshot |",
        f"| Inventory Status Distribution | `{facts['inventory_condition'].value}` | {facts['inventory_condition'].data_through_date} | No platform rollup rule |",
        "| YTD Actual CM | NULL | N/A | SOURCE_NOT_AVAILABLE |", "",
        "## Cutoff and comparison controls", "",
        f"- Sales/ads/inventory cutoff: `{facts['actual_sales'].data_through_date}`.",
        f"- CM cutoff: `{facts['actual_cm'].data_through_date}`.",
        "- No combined sales/CM common-cutoff metric was calculated.",
        f"- Weekly comparison: `{derived['weekly_sales_change'].availability.value}` using consecutive equal-length `WEEKLY_OPERATING` snapshots.",
        "- Freshness uses source states only; no unapproved day threshold was introduced.", "",
        f"- Source warnings: `{' | '.join(snapshot.warnings)}`.", "",
        "## Feishu dry-run", "", f"- Target: `{dry_run.target_table}`",
        f"- Health ID: `{dry_run.record['Health ID']}`",
        "- All health fields: `UNKNOWN` because no thresholds are approved.",
        "- `Data As Of` is blank because the evidence has mixed native cutoffs.",
        f"- Unmapped structured metrics: `{len(dry_run.diagnostics['unmapped_metrics'])}`.",
        "- External write performed: `false`.", "", "## Interpretation", "",
        "Overall status, primary driver, risk, opportunity, and required action remain `UNRESOLVED` pending human review.", "",
    ])


def render_preview_v2(snapshot: BusinessHealthSnapshot, dry_run: FeishuDryRun) -> str:
    """Render the calibrated management preview without activating proposed rules."""

    facts = snapshot.facts
    derived = snapshot.derived_control_metrics
    trend = derived["weekly_sales_change"].value
    inventory = facts["inventory_condition"].value or {}
    trend_text = "SOURCE_NOT_AVAILABLE"
    if trend is not None:
        trend_text = (
            f"{_number(trend['percent_change'], percent=True)} "
            f"({_number(trend['absolute_change'])} USD), "
            f"{trend['previous_period_start']}–{trend['previous_period_end']} vs "
            f"{trend['current_period_start']}–{trend['current_period_end']}"
        )
    pending = "PENDING_RULE_APPROVAL"
    return "\n".join([
        "# WALMART MP — BUSINESS HEALTH", "",
        f"**Control Week:** `{snapshot.control_week}`  ",
        "**Data Coverage:** `PARTIAL` — source lineage is validated, but native cutoffs differ and YTD CM is unavailable.", "",
        "## PERFORMANCE", "",
        f"- **Net Sales Actual / BP / Progress:** {_number(facts['actual_sales'].value)} / {_number(facts['bp_sales'].value)} USD / {_number(derived['sales_attainment_pct'].value, percent=True)}",
        f"- **Comparable Weekly Trend:** {trend_text}",
        f"- **Data Through:** {facts['actual_sales'].data_through_date} (`{facts['actual_sales'].period_type}` {facts['actual_sales'].period_start}–{facts['actual_sales'].period_end})", "",
        "## PROFITABILITY", "",
        f"- **CM Actual / BP / Progress:** {_number(facts['actual_cm'].value)} / {_number(facts['bp_cm'].value)} USD / {_number(derived['cm_attainment_pct'].value, percent=True)}",
        f"- **CM %:** {_number(derived['actual_cm_pct'].value, percent=True)} using CM-basis sales from the same accepted batch",
        f"- **Data Through:** {facts['actual_cm'].data_through_date} (`{facts['actual_cm'].period_type}` {facts['actual_cm'].period_start}–{facts['actual_cm'].period_end})", "",
        "## ADVERTISING", "",
        f"- **Spend / Attributed Sales / ROAS:** {_number(facts['ad_spend'].value)} / {_number(facts['attributed_ad_sales'].value)} USD / {_number(facts['roas'].value)}",
        f"- **Data Through:** {facts['ad_spend'].data_through_date} (`{facts['ad_spend'].period_type}` {facts['ad_spend'].period_start}–{facts['ad_spend'].period_end})", "",
        "## INVENTORY", "",
        f"- **Available Units:** {_number(facts['inventory_units'].value)}",
        f"- **SKU Availability:** In Stock {inventory.get('In Stock', 0)} / Out of Stock {inventory.get('Out of Stock', 0)} / Not Applicable {inventory.get('NOT_APPLICABLE', 0)}",
        f"- **Data Through:** {facts['inventory_condition'].data_through_date} (`SNAPSHOT`)", "",
        "## DATA COVERAGE", "",
        f"- Sales: `AVAILABLE`, through {facts['actual_sales'].data_through_date}",
        f"- CM: `AVAILABLE`, through {facts['actual_cm'].data_through_date}",
        f"- Ads: `AVAILABLE`, through {facts['ad_spend'].data_through_date}",
        f"- Inventory: facts `AVAILABLE`; platform health rollup `UNRESOLVED`, through {facts['inventory_condition'].data_through_date}",
        "- YTD CM: `SOURCE_NOT_AVAILABLE`", "",
        "## CONTROL", "",
        f"- Sales Health: `{pending}`",
        f"- CM Health: `{pending}`",
        f"- Ad Health: `{pending}`",
        f"- Inventory Health: `{pending}`",
        f"- Overall Health: `{pending}`",
        f"- Data Confidence: `{pending}`",
        f"- Primary Driver: `{pending}`",
        f"- Key Risk: `{pending}`",
        f"- Key Opportunity: `{pending}`",
        "- Required Action: `HUMAN_REVIEW_REQUIRED`; no Action was created.", "",
        "The Feishu payload remains a dry run. No rule, schema change, Signal, Action, or external write was activated.", "",
    ])


APPROVED_PHASE2C_FIELDS = {
    "CM Health": {
        "type": "single_select",
        "options": ["GREEN", "YELLOW", "RED", "UNKNOWN"],
    },
    "Data Confidence": {
        "type": "single_select",
        "options": ["HIGH", "MEDIUM", "LOW", "UNKNOWN"],
    },
}


def _activated_record(snapshot: BusinessHealthSnapshot) -> tuple[dict[str, Any], str]:
    if not snapshot.rule_evaluations:
        raise FeishuMappingError("BUSINESS_HEALTH_RULES_V1_NOT_ACTIVATED")
    facts = snapshot.facts
    derived = snapshot.derived_control_metrics
    trend = derived["weekly_sales_change"].value
    top_change = None
    if trend is not None:
        top_change = (
            f"Equal-length weekly net sales changed {_number(trend['percent_change'], percent=True)} "
            f"({_number(trend['absolute_change'])} USD): {trend['previous_period_start']}–{trend['previous_period_end']} "
            f"vs {trend['current_period_start']}–{trend['current_period_end']}."
        )
    sales_cutoff = snapshot.data_status["sales"].data_through_date
    cm_cutoff = snapshot.data_status["cm_actual"].data_through_date
    weekly_summary = (
        f"Walmart net sales {_number(facts['actual_sales'].value)} USD through {sales_cutoff}; "
        f"BP sales {_number(facts['bp_sales'].value)} USD; attainment {_number(derived['sales_attainment_pct'].value, percent=True)}; "
        f"Sales Health {snapshot.interpretation['sales_status']}. Actual CM {_number(facts['actual_cm'].value)} USD "
        f"through {cm_cutoff}; BP CM {_number(facts['bp_cm'].value)} USD; CM attainment "
        f"{_number(derived['cm_attainment_pct'].value, percent=True)}; CM% "
        f"{_number(derived['actual_cm_pct'].value, percent=True)}; CM Health {snapshot.interpretation['cm_status']}. "
        f"Native cutoffs are preserved."
    )
    return {
        "Health ID": mint_health_id(snapshot.control_week, snapshot.market, "WMT"),
        "Week": snapshot.control_week,
        "Market": snapshot.market,
        "Platform": "Walmart",
        "Level": snapshot.level,
        "Channel": None,
        "Overall Health": snapshot.interpretation["overall_status"],
        "Sales Health": snapshot.interpretation["sales_status"],
        "CM Health": snapshot.interpretation["cm_status"],
        "Ads Health": snapshot.interpretation["ads_status"],
        "Inventory Health": snapshot.interpretation["inventory_status"],
        "Weekly Summary": weekly_summary,
        "Top Change": top_change,
        "Data Completeness": "PARTIAL",
        "Data Confidence": snapshot.interpretation["data_confidence"],
        "Data As Of": None,
        "Source Type": "MIXED",
        "Source Ref": (
            f"Walmart run {facts['actual_sales'].source_release}; "
            f"STORM batch {facts['actual_cm'].import_batch_id}"
        ),
        "Human Reviewed": False,
        "Snapshot Locked": False,
    }, weekly_summary


def build_feishu_write_candidate(
    snapshot: BusinessHealthSnapshot,
    schema_path: str | Path,
    *,
    live_schema_validated: bool = False,
    live_record_lookup_performed: bool = False,
) -> FeishuWriteCandidate:
    """Build and validate a write candidate without invoking any record API."""

    schema = yaml.safe_load(Path(schema_path).read_text(encoding="utf-8"))
    table = next(item for item in schema["tables"] if item["name"] == "01 Business Health")
    existing = {item["name"]: item for item in table["fields"]}
    present_delta = set(APPROVED_PHASE2C_FIELDS) & set(existing)
    for name in present_delta:
        actual = existing[name]
        expected = APPROVED_PHASE2C_FIELDS[name]
        if actual.get("type") != expected["type"] or actual.get("options") != expected["options"]:
            raise FeishuMappingError(f"PHASE2C_FIELD_CONTRACT_MISMATCH: {name}")
    missing_delta = sorted(set(APPROVED_PHASE2C_FIELDS) - set(existing))
    allowed_fields = set(existing) | set(APPROVED_PHASE2C_FIELDS)
    record, _ = _activated_record(snapshot)
    unknown = set(record) - allowed_fields
    if unknown:
        raise FeishuMappingError(f"UNKNOWN_FEISHU_FIELDS: {sorted(unknown)}")
    required = {item["name"] for item in table["fields"] if item.get("required")}
    missing_required = {name for name in required if name not in record or record[name] is None}
    if missing_required:
        raise FeishuMappingError(f"REQUIRED_FEISHU_FIELDS_MISSING: {sorted(missing_required)}")
    expected_id = "HLT-2026W33-US-WMT"
    if snapshot.control_week == "2026-W33" and record["Health ID"] != expected_id:
        raise FeishuMappingError("HEALTH_ID_CONTRACT_MISMATCH")

    update_names = {
        "Overall Health", "Sales Health", "CM Health", "Ads Health", "Inventory Health",
        "Weekly Summary", "Top Change", "Data Completeness", "Data Confidence",
        "Data As Of", "Source Type", "Source Ref",
    }
    update_fields = {name: value for name, value in record.items() if name in update_names}
    omitted_fields = {
        "Buyability Health": "No approved Phase 2C rule.",
        "Listing Health": "No approved Phase 2C rule.",
        "Fulfillment Health": "No approved Phase 2C rule.",
        "Review Health": "No approved Phase 2C rule.",
        "Project Health": "Not a v1 Overall Health input.",
        "Top Risk": "No approved deterministic or human source.",
        "Top Opportunity": "No approved deterministic or human source.",
        "Next Priority": "No approved Action or human management input.",
        "Last Reviewed At": "Human review has not occurred.",
        "Created At": "Feishu system-managed field.",
        "Updated At": "Feishu system-managed field.",
    }
    live_table = schema["live_identifiers"]["tables"]["01 Business Health"]
    live_field_ids = {
        name: live_table["fields"][name]
        for name in record
        if name in live_table["fields"]
    }
    unmapped_control_inputs = [
        "actual_sales", "bp_sales", "sales_attainment_pct", "actual_cm", "bp_cm",
        "cm_attainment_pct", "actual_cm_pct", "ad_spend", "attributed_ad_sales", "roas",
        "inventory_condition", "weekly_sales_change",
    ]
    diagnostic_only = ["inventory_units", "ytd_actual_cm"]
    validation_basis = (
        "LIVE_SCHEMA" if not missing_delta and live_schema_validated
        else "LOCAL_APPROVED_DELTA_OVERLAY_PENDING_LIVE_SCHEMA"
    )
    return FeishuWriteCandidate(
        mode="LIVE_WRITE_CANDIDATE_ONLY",
        target={
            "base_name": schema["base"]["name"],
            "base_token": "RUNTIME_ONLY_NOT_PERSISTED",
            "table_name": table["name"],
            "table_id": live_table["table_id"],
            "field_ids": live_field_ids,
        },
        identity={
            "record_identity": record["Health ID"],
            "upsert_key": "Health ID",
            "expected_behavior": "CREATE_IF_NO_MATCH; UPDATE_MACHINE_OWNED_FIELDS_IF_EXACTLY_ONE_MATCH; ABORT_IF_DUPLICATE",
            "live_match_status": (
                "LOOKUP_PERFORMED" if live_record_lookup_performed else "NOT_CHECKED_NO_RUNTIME_BASE_TOKEN"
            ),
        },
        create_fields=record,
        update_fields=update_fields,
        omitted_fields=omitted_fields,
        source_snapshot_ids={
            "walmart_official_run_id": snapshot.facts["actual_sales"].source_release,
            "walmart_business_artifact": snapshot.facts["actual_sales"].source_artifact,
            "walmart_inventory_artifact": snapshot.facts["inventory_condition"].source_artifact,
            "structured_metrics_batch_id": snapshot.facts["actual_cm"].import_batch_id,
            "structured_metrics_release": snapshot.facts["actual_cm"].source_release,
        },
        data_through_dates={
            "sales": snapshot.data_status["sales"].data_through_date,
            "cm": snapshot.data_status["cm_actual"].data_through_date,
            "advertising": snapshot.data_status["advertising"].data_through_date,
            "inventory": snapshot.data_status["inventory"].data_through_date,
            "weekly_trend": snapshot.data_status["weekly_trend"].data_through_date,
        },
        mapping_review={
            "mapped_fields": sorted(record),
            "remaining_unmapped_control_inputs": unmapped_control_inputs,
            "diagnostic_only_fields": diagnostic_only,
            "intentionally_omitted_fields": sorted(omitted_fields),
            "management_concepts_without_dedicated_field": ["Primary Driver"],
        },
        validation={
            "schema_validation_basis": validation_basis,
            "deployment_status": schema["live_identifiers"]["deployment_status"],
            "base_resource_fingerprint": schema["live_identifiers"]["base_resource_fingerprint"],
            "local_checkpoint_field_count_before": len(existing),
            "approved_fields_missing_from_local_checkpoint": missing_delta,
            "candidate_field_count_after": len(existing) + len(missing_delta),
            "only_approved_schema_delta": missing_delta in [[], sorted(APPROVED_PHASE2C_FIELDS)],
            "live_schema_validated": live_schema_validated,
            "record_api_invoked": False,
            "external_record_write_performed": False,
        },
    )


def render_preview_v3(snapshot: BusinessHealthSnapshot, candidate: FeishuWriteCandidate) -> str:
    facts = snapshot.facts
    derived = snapshot.derived_control_metrics
    rules = snapshot.rule_evaluations
    trend = derived["weekly_sales_change"].value
    inventory = facts["inventory_condition"].value or {}
    trend_text = "SOURCE_NOT_AVAILABLE"
    if trend is not None:
        trend_text = (
            f"{_number(trend['percent_change'], percent=True)} ({_number(trend['absolute_change'])} USD), "
            f"{trend['previous_period_start']}–{trend['previous_period_end']} vs "
            f"{trend['current_period_start']}–{trend['current_period_end']}"
        )
    return "\n".join([
        "# WALMART MP — BUSINESS HEALTH CONTROL PLANE", "",
        f"- **Platform:** `WALMART_MP`",
        f"- **Control Week:** `{snapshot.control_week}`",
        f"- **Overall Health:** `{snapshot.interpretation['overall_status']}`",
        f"- **Data Confidence:** `{snapshot.interpretation['data_confidence']}`", "",
        "## PERFORMANCE", "",
        f"- Actual Sales: {_number(facts['actual_sales'].value)} USD",
        f"- BP Sales: {_number(facts['bp_sales'].value)} USD",
        f"- Attainment: {_number(derived['sales_attainment_pct'].value, percent=True)}",
        f"- Weekly Trend: {trend_text}",
        f"- Sales Health: `{rules['sales_health'].result}` — {rules['sales_health'].reason}",
        f"- Data Through: {facts['actual_sales'].data_through_date} (`{facts['actual_sales'].period_type}` {facts['actual_sales'].period_start}–{facts['actual_sales'].period_end})", "",
        "## PROFITABILITY", "",
        f"- Actual CM: {_number(facts['actual_cm'].value)} USD",
        f"- BP CM: {_number(facts['bp_cm'].value)} USD",
        f"- Attainment: {_number(derived['cm_attainment_pct'].value, percent=True)}",
        f"- CM%: {_number(derived['actual_cm_pct'].value, percent=True)}",
        f"- CM Health: `{rules['cm_health'].result}` — {rules['cm_health'].reason}",
        f"- Data Through: {facts['actual_cm'].data_through_date} (`{facts['actual_cm'].period_type}` {facts['actual_cm'].period_start}–{facts['actual_cm'].period_end})", "",
        "## ADVERTISING", "",
        f"- Spend: {_number(facts['ad_spend'].value)} USD",
        f"- Attributed Sales: {_number(facts['attributed_ad_sales'].value)} USD",
        f"- ROAS: {_number(facts['roas'].value)}",
        f"- Ad Health: `{rules['advertising_health'].result}` — {rules['advertising_health'].reason}",
        f"- Data Through: {facts['ad_spend'].data_through_date} (`{facts['ad_spend'].period_type}` {facts['ad_spend'].period_start}–{facts['ad_spend'].period_end})", "",
        "## INVENTORY", "",
        f"- Available Units: {_number(facts['inventory_units'].value)}",
        f"- SKU Availability: In Stock {inventory.get('In Stock', 0)} / Out of Stock {inventory.get('Out of Stock', 0)} / Not Applicable {inventory.get('NOT_APPLICABLE', 0)}",
        f"- Inventory Health: `{rules['inventory_health'].result}` — {rules['inventory_health'].reason}",
        f"- Data Through: {facts['inventory_condition'].data_through_date} (`SNAPSHOT`)", "",
        "## MANAGEMENT CONTROL", "",
        f"- Overall Health: `{snapshot.interpretation['overall_status']}`",
        f"- Data Confidence: `{snapshot.interpretation['data_confidence']}` — {rules['data_confidence'].reason}",
        f"- Primary Driver: {snapshot.interpretation['primary_driver']}",
        "- Key Risk: `UNRESOLVED`",
        "- Key Opportunity: `UNRESOLVED`",
        "- Required Action: `UNRESOLVED` — no approved Action or human input.", "",
        "## WRITE CONTROL", "",
        f"- Candidate identity: `{candidate.identity['record_identity']}`",
        f"- Schema validation: `{candidate.validation['schema_validation_basis']}`",
        "- Record API invoked: `false`",
        "- External record write performed: `false`", "",
    ])
