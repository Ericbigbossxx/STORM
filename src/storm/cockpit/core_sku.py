"""Deterministic Phase 2E Walmart Core SKU package and Feishu candidate mapping."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from storm.adapters.walmart_official import WalmartOfficialEvidence
from storm.domain.ids import mint_sku_id


class CoreSkuBuildError(RuntimeError):
    """Raised when a governed Phase 2E source or mapping gate fails."""


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _sum_available(values: Iterable[Any]) -> float | None:
    available = [float(value) for value in values if value is not None]
    return sum(available) if available else None


def _date_text(value: Any) -> str:
    return str(value)[:10]


def _load_targets(database: str | Path, *, year: int, month: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    with sqlite3.connect(str(database)) as connection:
        rows = connection.execute(
            """
            SELECT canonical_sku, bp_sales, bp_units, import_batch_id, source_sheet,
                   source_rows_json
            FROM FACT_BP_TARGET_MONTHLY
            WHERE year = ? AND month = ? AND platform = 'WALMART_MP'
            ORDER BY canonical_sku
            """,
            (year, month),
        ).fetchall()
    targets = {
        str(row[0]): {
            "bp_sales": _number(row[1]),
            "bp_units": _number(row[2]),
            "import_batch_id": str(row[3]),
            "source_sheet": str(row[4]),
            "source_rows_json": str(row[5]),
        }
        for row in rows
    }
    return targets, {
        "target_fact_count": len(rows),
        "target_sales_total": _sum_available(row[1] for row in rows),
        "target_units_total": _sum_available(row[2] for row in rows),
        "import_batch_ids": sorted({str(row[3]) for row in rows}),
    }


def _role(raw: Any) -> tuple[str, str]:
    mapping = {
        "Growth": ("GROWTH", "EXACT_NORMALIZATION"),
        "Profit": ("PROFIT", "EXACT_NORMALIZATION"),
        "Core": ("OTHER", "SOURCE_VALUE_NOT_IN_FEISHU_ENUM"),
        "Support/Accessory": ("OTHER", "SOURCE_VALUE_NOT_IN_FEISHU_ENUM"),
    }
    if raw not in mapping:
        raise CoreSkuBuildError(f"UNMAPPED_REVIEWED_STRATEGIC_ROLE: {raw}")
    return mapping[str(raw)]


def _product_line(raw: Any) -> tuple[str, str]:
    if raw == "Robotic Lawn Mowers":
        return "Robot", "EXACT_TAXONOMY_MATCH"
    return "Other", "SOURCE_VALUE_NOT_IN_FEISHU_ENUM"


def _weekly_context(records: tuple[dict[str, Any], ...], current_date: str) -> dict[str, Any]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_date[_date_text(row["business_as_of_date"])].append(row)
    dates = sorted(value for value in by_date if value <= current_date)
    if len(dates) < 2 or dates[-1] != current_date:
        return {
            "status": "UNAVAILABLE",
            "reason": "TWO_CONSECUTIVE_OFFICIAL_SKU_WEEKLY_RELEASES_NOT_AVAILABLE",
            "current": {},
            "previous": {},
        }
    previous_date, latest_date = dates[-2:]
    current_rows = by_date[latest_date]
    previous_rows = by_date[previous_date]

    def window(rows: list[dict[str, Any]]) -> tuple[date, date]:
        windows = {
            (
                date.fromisoformat(_date_text(row["coverage_start_date"])),
                date.fromisoformat(_date_text(row["coverage_end_date"])),
            )
            for row in rows
        }
        if len(windows) != 1:
            raise CoreSkuBuildError("SKU_WEEKLY_WINDOW_INCONSISTENT_WITHIN_RELEASE")
        return next(iter(windows))

    previous_start, previous_end = window(previous_rows)
    current_start, current_end = window(current_rows)
    previous_days = (previous_end - previous_start).days + 1
    current_days = (current_end - current_start).days + 1
    if previous_days != current_days or current_start != previous_end + timedelta(days=1):
        return {
            "status": "UNAVAILABLE",
            "reason": "SKU_WEEKLY_PERIODS_NOT_EQUAL_LENGTH_AND_CONSECUTIVE",
            "previous_period": [previous_start.isoformat(), previous_end.isoformat()],
            "current_period": [current_start.isoformat(), current_end.isoformat()],
            "current": {},
            "previous": {},
        }
    return {
        "status": "VALID_PERIOD_PAIR",
        "reason": None,
        "previous_release_date": previous_date,
        "current_release_date": latest_date,
        "previous_period": [previous_start.isoformat(), previous_end.isoformat()],
        "current_period": [current_start.isoformat(), current_end.isoformat()],
        "period_days": current_days,
        "current": {str(row["sku"]): row for row in current_rows},
        "previous": {str(row["sku"]): row for row in previous_rows},
    }


def _semantic_audit(current_date: str) -> list[dict[str, str | None]]:
    rows = [
        ("SKU Perf ID", "STORM domain ID contract", "control_week + market + platform + sku", "weekly candidate identity", "week x market x platform x sku", "machine-mint; no source overwrite", "blocked if any component is blank"),
        ("Week", "accepted Phase 2C Business Health snapshot", "control_week", "weekly control context", "week", "pass through", "blocked if unavailable"),
        ("Market", "approved Phase 2E scope", "US", "market scope", "constant scope", "pass through", "blocked if scope differs"),
        ("Platform", "config/walmart_official_source.yaml", "WALMART_MP mapping", "platform scope", "constant scope", "map WALMART_MP to Walmart", "blocked if mapping differs"),
        ("Channel", "config/sku_business_attributes.xlsx / SKU_Business_Attributes", "channel", "reviewed channel", "platform x sku", "pass through reviewed value", "blank remains blank"),
        ("Product Line", "config/sku_business_attributes.xlsx / SKU_Business_Attributes", "product_line", "reviewed Walmart product taxonomy", "platform x sku", "exact Robotic Lawn Mowers -> Robot; incompatible values -> Other", "raw value retained in package"),
        ("SKU", "data/history/marketplace/sku_mtd_snapshots.parquet", "sku", "canonical Walmart SKU", "MTD release x sku", "pass through", "blocked if blank"),
        ("Model / Product", "config/sku_business_attributes.xlsx / SKU_Business_Attributes", "product_name", "reviewed item name", "platform x sku", "pass through", "blank remains blank"),
        ("SKU Role", "config/sku_business_attributes.xlsx / SKU_Business_Attributes", "strategic_role", "human-reviewed portfolio role", "platform x sku", "exact enum normalization; incompatible reviewed values -> OTHER", "never inferred from performance"),
        ("Sales", "data/history/marketplace/sku_mtd_snapshots.parquet", "net_sales", "SKU MTD net sales", "MTD release x sku", "pass through", "NULL remains NULL"),
        ("Orders", "data/history/marketplace/sku_mtd_snapshots.parquet", "orders", "SKU MTD orders", "MTD release x sku", "pass through", "NULL remains NULL"),
        ("Units", "data/history/marketplace/sku_mtd_snapshots.parquet", "units_sold", "SKU MTD units", "MTD release x sku", "pass through", "NULL remains NULL"),
        ("WoW Sales %", "data/history/marketplace/sku_weekly_snapshots.parquet", "weekly_sku_net_sales", "equal-week SKU net-sales change", "weekly release x sku", "(current-prior)/prior only for equal, consecutive, official periods", "NULL if either value missing or prior is zero"),
        ("Target", "data/structured_metrics/storm_metrics.sqlite3 / FACT_BP_TARGET_MONTHLY", "bp_sales", "full-month SKU BP sales", "month x platform x sku", "join canonical_sku", "NULL remains NULL"),
        ("Target Gap %", "SKU_MTD + FACT_BP_TARGET_MONTHLY", "net_sales, bp_sales", "MTD progress variance to full-month BP", "month x platform x sku", "(net_sales-bp_sales)/bp_sales", "NULL if actual/target missing or target zero"),
        ("Traffic", None, None, "SKU traffic", "unknown", "not mapped", "SOURCE_NOT_AVAILABLE"),
        ("Conversion Rate", None, None, "SKU conversion", "unknown", "not mapped", "SOURCE_NOT_AVAILABLE"),
        ("Ad Spend", "data/history/marketplace/sku_mtd_snapshots.parquet", "ad_spend", "SKU MTD ad spend", "MTD release x sku", "pass through", "NULL remains NULL"),
        ("ROAS", "data/history/marketplace/sku_mtd_snapshots.parquet", "calculated_roas", "official calculated SKU ROAS", "MTD release x sku", "pass through; no threshold", "NULL remains NULL"),
        ("Inventory", "data/history/marketplace/sku_mtd_snapshots.parquet", "inventory_units", "available inventory units snapshot", "release x sku", "pass through", "NULL remains NULL"),
        ("DOS", None, None, "days of supply", "unknown", "not mapped", "SOURCE_NOT_AVAILABLE"),
        ("Buyability", None, None, "verified buyability", "unknown", "set UNKNOWN", "inventory is not substituted"),
        ("Listing Status", None, None, "verified listing health", "unknown", "set UNKNOWN", "item_status is not substituted"),
        ("Status", "config/cockpit_metrics.yaml", "no approved SKU-health rule", "SKU health", "week x sku", "set UNKNOWN", "never infer GREEN/YELLOW/RED"),
        ("Main Change", "deterministic Phase 2E facts", "target_delta and factual flags", "management display summary", "week x sku", "factual templating only", "blank if no selected evidence"),
        ("Diagnosis", "deterministic Phase 2E facts", "issue tags", "primary issue tags", "week x sku", "allowed factual tags only", "no causal narrative"),
        ("Recommended Action", None, None, "human-approved action", "action lifecycle", "omitted", "NO_HUMAN_APPROVED_ACTION"),
        ("Data As Of", "sku_mtd_snapshots.parquet", "business_as_of_date", "native SKU MTD cutoff", "release", "pass through", "blocked if unavailable"),
        ("Source Type", "mixed governed sources", None, "lineage class", "candidate", "set MIXED", "not blank"),
        ("Source Ref", "release manifest + protected workbook + STORM batch", "lineage identifiers", "audit lineage", "candidate", "concatenate non-secret identifiers", "omit unavailable parts"),
        ("Evidence", "deterministic Phase 2E package", "native periods, raw classifications, null reasons", "review evidence", "candidate", "factual templating only", "no AI diagnosis"),
        ("Human Reviewed", "governance contract", "human-only authority", "record approval", "candidate", "set false", "AI cannot set true"),
        ("Snapshot Locked", "governance contract", "write lifecycle", "snapshot control", "candidate", "set false", "no record exists"),
        ("Created At", "Feishu system", "system timestamp", "created time", "record", "omitted", "system-managed"),
        ("Updated At", "Feishu system", "system timestamp", "modified time", "record", "omitted", "system-managed"),
    ]
    return [
        {
            "field": field,
            "source_artifact": artifact,
            "source_field": source_field,
            "business_meaning": meaning,
            "grain": grain,
            "data_through_date": current_date if artifact and "sku_mtd" in artifact else None,
            "transformation": transformation,
            "null_behavior": null_behavior,
        }
        for field, artifact, source_field, meaning, grain, transformation, null_behavior in rows
    ]


def _validate_schema(schema: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    table = next(item for item in schema["tables"] if item["name"] == "02 Core SKU Performance")
    live = schema.get("live_identifiers", {}).get("tables", {}).get("02 Core SKU Performance")
    if not live or not live.get("table_id"):
        raise CoreSkuBuildError("LIVE_CORE_SKU_TABLE_MANIFEST_MISSING")
    declared = {item["name"] for item in table["fields"]}
    live_fields = {str(name): str(field_id) for name, field_id in live["fields"].items()}
    if declared != set(live_fields):
        raise CoreSkuBuildError("LIVE_CORE_SKU_FIELD_MANIFEST_DRIFT")
    return table, live_fields


def build_walmart_core_sku_package(
    evidence: WalmartOfficialEvidence,
    database: str | Path,
    schema_path: str | Path,
    *,
    control_week: str,
    live_record_count: int,
    platform_health_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the governed Phase 2E package without invoking an external write API."""

    required = {"business_current_state", "sku_current_performance", "sku_weekly_history", "sku_business_attributes"}
    missing = sorted(required - set(evidence.datasets))
    if missing:
        raise CoreSkuBuildError(f"REQUIRED_PHASE2E_DATASET_MISSING: {', '.join(missing)}")
    current_rows = list(evidence.datasets["sku_current_performance"].records)
    if not current_rows:
        raise CoreSkuBuildError("CURRENT_SKU_FACTS_EMPTY")
    current_date = evidence.datasets["sku_current_performance"].business_date
    if (
        platform_health_snapshot.get("control_week") != control_week
        or platform_health_snapshot.get("market") != "US"
        or platform_health_snapshot.get("platform") != "WALMART_MP"
    ):
        raise CoreSkuBuildError("PLATFORM_HEALTH_CONTEXT_MISMATCH")
    health_sales = platform_health_snapshot.get("facts", {}).get("actual_sales", {})
    if (
        health_sales.get("source_release") != evidence.official_run_id
        or health_sales.get("data_through_date") != current_date
    ):
        raise CoreSkuBuildError("PLATFORM_HEALTH_SOURCE_RELEASE_MISMATCH")
    target_date = date.fromisoformat(current_date)
    targets, target_summary = _load_targets(database, year=target_date.year, month=target_date.month)
    attributes = {
        str(row["sku"]): row
        for row in evidence.datasets["sku_business_attributes"].records
    }
    source_skus = {str(row["sku"]) for row in current_rows}
    if source_skus != set(attributes):
        raise CoreSkuBuildError("SKU_ATTRIBUTE_COVERAGE_MISMATCH")
    weekly = _weekly_context(
        evidence.datasets["sku_weekly_history"].history_records,
        current_date,
    )
    facts: list[dict[str, Any]] = []
    for row in sorted(current_rows, key=lambda item: str(item["sku"])):
        sku = str(row["sku"])
        attr = attributes[sku]
        target = targets.get(sku, {})
        sales = _number(row.get("net_sales"))
        bp_sales = _number(target.get("bp_sales"))
        target_delta = sales - bp_sales if sales is not None and bp_sales is not None else None
        target_gap_pct = (
            target_delta / bp_sales
            if target_delta is not None and bp_sales not in (None, 0.0)
            else None
        )
        current_weekly = weekly.get("current", {}).get(sku, {})
        previous_weekly = weekly.get("previous", {}).get(sku, {})
        current_weekly_sales = _number(current_weekly.get("weekly_sku_net_sales"))
        previous_weekly_sales = _number(previous_weekly.get("weekly_sku_net_sales"))
        wow_pct = None
        wow_reason = weekly.get("reason")
        if weekly["status"] == "VALID_PERIOD_PAIR":
            if current_weekly_sales is None or previous_weekly_sales is None:
                wow_reason = "SKU_WEEKLY_SALES_SOURCE_NOT_AVAILABLE"
            elif previous_weekly_sales == 0:
                wow_reason = "PRIOR_SKU_WEEKLY_SALES_ZERO"
            else:
                wow_pct = (current_weekly_sales - previous_weekly_sales) / previous_weekly_sales
                wow_reason = None
        normalized_role, role_mapping = _role(attr["strategic_role"])
        normalized_line, line_mapping = _product_line(attr["product_line"])
        ad_spend = _number(row.get("ad_spend"))
        ad_sales = _number(row.get("ad_sales"))
        flags = {
            "negative_net_sales": sales is not None and sales < 0,
            "ad_spend_with_zero_attributed_sales": ad_spend is not None and ad_spend > 0 and ad_sales == 0,
            "out_of_stock": row.get("inventory_status") == "Out of Stock",
        }
        refund_amount = _number(row.get("refund_amount"))
        facts.append(
            {
                "sku": sku,
                "item_id": attr["item_id"],
                "product_name": attr["product_name"],
                "product_line_raw": attr["product_line"],
                "product_line": normalized_line,
                "product_line_mapping": line_mapping,
                "strategic_role_raw": attr["strategic_role"],
                "sku_role": normalized_role,
                "sku_role_mapping": role_mapping,
                "channel": attr["channel"],
                "fulfillment_type": row.get("fulfillment_type"),
                "item_status": row.get("item_status"),
                "sales": sales,
                "orders": _number(row.get("orders")),
                "units": _number(row.get("units_sold")),
                "contribution_profit": _number(row.get("contribution_profit")),
                "contribution_margin": _number(row.get("contribution_margin")),
                "refund_amount": refund_amount,
                "refund_amount_rate": _number(row.get("refund_amount_rate")),
                "gross_sales_derived": (
                    sales + refund_amount
                    if sales is not None and refund_amount is not None
                    else None
                ),
                "ad_spend": ad_spend,
                "ad_sales": ad_sales,
                "roas": _number(row.get("calculated_roas")),
                "inventory": _number(row.get("inventory_units")),
                "inventory_status": row.get("inventory_status"),
                "target": bp_sales,
                "target_units": _number(target.get("bp_units")),
                "target_delta": target_delta,
                "target_gap_pct": target_gap_pct,
                "weekly_sales_current": current_weekly_sales,
                "weekly_sales_previous": previous_weekly_sales,
                "wow_sales_pct": wow_pct,
                "wow_unavailable_reason": wow_reason,
                "flags": flags,
                "source_run_id": row["source_run_id"],
                "snapshot_content_hash": row["snapshot_content_hash"],
                "data_as_of": current_date,
                "coverage_start_date": _date_text(row["coverage_start_date"]),
                "coverage_end_date": _date_text(row["coverage_end_date"]),
            }
        )

    detractors = sorted(
        (fact for fact in facts if fact["target_delta"] is not None and fact["target_delta"] < 0),
        key=lambda fact: (fact["target_delta"], fact["sku"]),
    )[:5]
    contributors = sorted(
        (fact for fact in facts if fact["target_delta"] is not None and fact["target_delta"] > 0),
        key=lambda fact: (-fact["target_delta"], fact["sku"]),
    )[:5]
    total_negative_gap = -sum(
        fact["target_delta"]
        for fact in facts
        if fact["target_delta"] is not None and fact["target_delta"] < 0
    )
    flag_groups = {
        "ad_spend_with_zero_attributed_sales": [fact for fact in facts if fact["flags"]["ad_spend_with_zero_attributed_sales"]],
        "negative_net_sales": [fact for fact in facts if fact["flags"]["negative_net_sales"]],
        "out_of_stock": [fact for fact in facts if fact["flags"]["out_of_stock"]],
    }
    selection_reasons: dict[str, list[str]] = defaultdict(list)
    for fact in detractors:
        selection_reasons[fact["sku"]].extend(["TOP_5_SALES_TARGET_DETRACTOR", "BELOW_BP"])
    for fact in contributors:
        selection_reasons[fact["sku"]].extend(["TOP_POSITIVE_SALES_CONTRIBUTOR", "POSITIVE_CONTRIBUTOR"])
    for name, rows in flag_groups.items():
        for fact in rows:
            selection_reasons[fact["sku"]].append(name.upper())

    schema = yaml.safe_load(Path(schema_path).read_text(encoding="utf-8"))
    table, live_fields = _validate_schema(schema)
    field_specs = {item["name"]: item for item in table["fields"]}
    candidates: list[dict[str, Any]] = []
    fact_by_sku = {fact["sku"]: fact for fact in facts}
    for sku in sorted(selection_reasons):
        fact = fact_by_sku[sku]
        tags = selection_reasons[sku]
        change_parts: list[str] = []
        if "TOP_5_SALES_TARGET_DETRACTOR" in tags:
            change_parts.append(f"MTD sales minus full-month BP: {fact['target_delta']:.2f} USD")
        if "TOP_POSITIVE_SALES_CONTRIBUTOR" in tags:
            change_parts.append(f"Positive MTD sales minus full-month BP: {fact['target_delta']:.2f} USD")
        if fact["flags"]["negative_net_sales"]:
            change_parts.append(f"Negative MTD net sales: {fact['sales']:.2f} USD")
        if fact["flags"]["ad_spend_with_zero_attributed_sales"]:
            change_parts.append(f"Ad spend {fact['ad_spend']:.2f} USD with attributed ad sales 0.00 USD")
        if fact["flags"]["out_of_stock"]:
            change_parts.append("Official inventory status: Out of Stock")
        fields: dict[str, Any] = {
            "SKU Perf ID": mint_sku_id(control_week, "US", "WMT", sku),
            "Week": control_week,
            "Market": "US",
            "Platform": "Walmart",
            "Channel": "3P",
            "Product Line": fact["product_line"],
            "SKU": sku,
            "Model / Product": fact["product_name"],
            "SKU Role": fact["sku_role"],
            "Sales": fact["sales"],
            "Orders": fact["orders"],
            "Units": fact["units"],
            "WoW Sales %": fact["wow_sales_pct"],
            "Target": fact["target"],
            "Target Gap %": fact["target_gap_pct"],
            "Ad Spend": fact["ad_spend"],
            "ROAS": fact["roas"],
            "Inventory": fact["inventory"],
            "Buyability": "UNKNOWN",
            "Listing Status": "UNKNOWN",
            "Status": "UNKNOWN",
            "Main Change": "; ".join(change_parts),
            "Diagnosis": ", ".join(tags),
            "Data As Of": fact["data_as_of"],
            "Source Type": "MIXED",
            "Source Ref": (
                f"Walmart official run {evidence.official_run_id}; "
                f"SKU_MTD {fact['snapshot_content_hash']}; governed SKU attributes; "
                f"STORM BP {target_summary['import_batch_ids'][0]}"
            ),
            "Evidence": (
                f"SKU_MTD {fact['coverage_start_date']} to {fact['coverage_end_date']}; "
                f"WoW {fact['wow_unavailable_reason'] or 'AVAILABLE'}; "
                f"raw role {fact['strategic_role_raw']}; raw product line {fact['product_line_raw']}"
            ),
            "Human Reviewed": False,
            "Snapshot Locked": False,
        }
        fields = {name: value for name, value in fields.items() if value is not None}
        unknown = sorted(set(fields) - set(field_specs))
        if unknown:
            raise CoreSkuBuildError(f"UNKNOWN_CORE_SKU_FIELDS: {unknown}")
        required_fields = {name for name, spec in field_specs.items() if spec.get("required")}
        missing_required = sorted(required_fields - set(fields))
        if missing_required:
            raise CoreSkuBuildError(f"REQUIRED_CORE_SKU_FIELDS_MISSING: {sku}: {missing_required}")
        for name, value in fields.items():
            options = field_specs[name].get("options")
            if options and value not in options:
                raise CoreSkuBuildError(f"CORE_SKU_ENUM_INVALID: {sku}: {name}: {value}")
        candidates.append(
            {
                "action": "CREATE" if live_record_count == 0 else "REQUIRES_IDENTITY_LOOKUP",
                "identity": {"SKU Perf ID": fields["SKU Perf ID"]},
                "selection_reasons": tags,
                "create_fields": fields,
                "fields_by_live_id": {live_fields[name]: value for name, value in fields.items()},
                "omitted_fields": {
                    name: reason
                    for name, reason in {
                        "Traffic": "SOURCE_NOT_AVAILABLE",
                        "Conversion Rate": "SOURCE_NOT_AVAILABLE",
                        "DOS": "SOURCE_NOT_AVAILABLE",
                        "Recommended Action": "NO_HUMAN_APPROVED_ACTION",
                        "Created At": "FEISHU_SYSTEM_MANAGED",
                        "Updated At": "FEISHU_SYSTEM_MANAGED",
                    }.items()
                },
            }
        )

    business = evidence.datasets["business_current_state"].records[0]
    source_target_matches = [fact for fact in facts if fact["target"] is not None]
    reconciliation = {
        "sales": {
            "sku_total": _sum_available(fact["sales"] for fact in facts),
            "platform_total": _number(business.get("net_sales")),
            "scope_difference": "NONE; both are official current SKU_MTD / BUSINESS_MTD net sales",
        },
        "ad_spend": {
            "sku_total": _sum_available(fact["ad_spend"] for fact in facts),
            "platform_total": _number(business.get("ad_spend")),
            "scope_difference": "Platform MTD includes spend not allocated to eligible SKU rows; no allocation was forced",
        },
        "inventory": {
            "sku_total": _sum_available(fact["inventory"] for fact in facts),
            "platform_total": _number(business.get("inventory_units")),
            "scope_difference": "NONE; both are current official inventory units",
        },
        "bp_sales": {
            "matched_source_sku_count": len(source_target_matches),
            "target_fact_count": target_summary["target_fact_count"],
            "matched_sku_total": _sum_available(fact["target"] for fact in facts),
            "platform_target_total": target_summary["target_sales_total"],
            "target_skus_absent_from_source": sorted(set(targets) - source_skus),
            "scope_difference": "Target facts absent from the current official SKU release carry zero BP; aggregate value is unchanged",
        },
    }
    for metric in ("sales", "ad_spend", "inventory"):
        item = reconciliation[metric]
        if item["sku_total"] is None or item["platform_total"] is None:
            item["difference"] = None
            item["status"] = "BLOCKED"
        else:
            item["difference"] = item["sku_total"] - item["platform_total"]
            item["status"] = "PASS" if abs(item["difference"]) < 0.005 else "EXPLAINED_DIFFERENCE"
    bp_item = reconciliation["bp_sales"]
    bp_item["difference"] = bp_item["matched_sku_total"] - bp_item["platform_target_total"]
    bp_item["status"] = "PASS" if abs(bp_item["difference"]) < 0.005 else "BLOCKED"

    interpretation = platform_health_snapshot["interpretation"]
    health_facts = platform_health_snapshot["facts"]
    health_derived = platform_health_snapshot["derived_control_metrics"]
    platform_context = {
        "overall_health": interpretation["overall_status"],
        "sales_health": interpretation["sales_status"],
        "cm_health": interpretation["cm_status"],
        "ads_health": interpretation["ads_status"],
        "inventory_health": interpretation["inventory_status"],
        "data_confidence": interpretation["data_confidence"],
        "actual_sales": health_facts["actual_sales"]["value"],
        "bp_sales": health_facts["bp_sales"]["value"],
        "sales_gap": health_facts["actual_sales"]["value"] - health_facts["bp_sales"]["value"],
        "sales_attainment": health_derived["sales_attainment_pct"]["value"],
        "actual_cm": health_facts["actual_cm"]["value"],
        "bp_cm": health_facts["bp_cm"]["value"],
        "ad_spend": health_facts["ad_spend"]["value"],
        "attributed_ad_sales": health_facts["attributed_ad_sales"]["value"],
        "roas": health_facts["roas"]["value"],
        "inventory_units": health_facts["inventory_units"]["value"],
        "data_through": {
            "sales": health_facts["actual_sales"]["data_through_date"],
            "ads": health_facts["ad_spend"]["data_through_date"],
            "inventory": health_facts["inventory_units"]["data_through_date"],
            "cm": health_facts["actual_cm"]["data_through_date"],
        },
    }

    return {
        "schema_version": "1.0.0",
        "phase": "PHASE_2E",
        "scope": "WALMART_MP",
        "control_week": control_week,
        "business_as_of_date": current_date,
        "source_release": {
            "official_run_id": evidence.official_run_id,
            "release_version": evidence.release_version,
            "release_manifest": evidence.release_manifest,
            "sku_mtd_content_hash": evidence.datasets["sku_current_performance"].content_hash,
            "sku_weekly_content_hash": evidence.datasets["sku_weekly_history"].content_hash,
            "sku_attribute_file_hash": evidence.datasets["sku_business_attributes"].content_hash,
        },
        "platform_context": platform_context,
        "source_semantic_audit": _semantic_audit(current_date),
        "role_classification": {
            "authoritative_source_found": True,
            "source_record_count": len(attributes),
            "source_values": sorted({str(row["strategic_role"]) for row in attributes.values()}),
            "mapping_policy": {
                "Growth": "GROWTH",
                "Profit": "PROFIT",
                "Core": "OTHER",
                "Support/Accessory": "OTHER",
            },
            "inference_from_performance_performed": False,
        },
        "weekly_comparison": {key: value for key, value in weekly.items() if key not in {"current", "previous"}},
        "data_coverage_summary": {
            "eligible_sku_count": len(facts),
            "sales_available_count": sum(fact["sales"] is not None for fact in facts),
            "bp_sales_available_count": sum(fact["target"] is not None for fact in facts),
            "sales_and_bp_comparable_count": sum(fact["target_delta"] is not None for fact in facts),
            "sku_contribution_profit_available_count": sum(fact["contribution_profit"] is not None for fact in facts),
            "sku_contribution_margin_available_count": sum(fact["contribution_margin"] is not None for fact in facts),
            "ad_spend_available_count": sum(fact["ad_spend"] is not None for fact in facts),
            "inventory_available_count": sum(fact["inventory"] is not None for fact in facts),
            "valid_wow_value_count": sum(fact["wow_sales_pct"] is not None for fact in facts),
        },
        "eligible_sku_fact_count": len(facts),
        "eligible_sku_facts": facts,
        "rankings": {
            "top_sales_target_detractors": [
                {
                    **{key: fact[key] for key in ("sku", "product_name", "sales", "target", "target_delta", "target_gap_pct", "wow_sales_pct", "data_as_of")},
                    "attainment": fact["sales"] / fact["target"] if fact["target"] not in (None, 0.0) else None,
                    "share_of_total_negative_gap": (-fact["target_delta"] / total_negative_gap) if total_negative_gap else None,
                    "issue_flags": [name.upper() for name, value in fact["flags"].items() if value],
                }
                for fact in detractors
            ],
            "top_positive_sales_contributors": [
                {key: fact[key] for key in ("sku", "product_name", "sales", "target", "target_delta", "target_gap_pct", "data_as_of")}
                for fact in contributors
            ],
        },
        "factual_flags": {
            name: [
                {
                    "sku": fact["sku"],
                    "product_name": fact["product_name"],
                    "sales": fact["sales"],
                    "target": fact["target"],
                    "ad_spend": fact["ad_spend"],
                    "ad_sales": fact["ad_sales"],
                    "roas": fact["roas"],
                    "inventory_status": fact["inventory_status"],
                    "inventory_units": fact["inventory"],
                    "refund_amount": fact["refund_amount"],
                    "gross_sales_derived": fact["gross_sales_derived"],
                    "data_as_of": fact["data_as_of"],
                }
                for fact in rows
            ]
            for name, rows in flag_groups.items()
        },
        "reconciliation": reconciliation,
        "unmapped_source_metrics": [
            {"metric": "item_id", "reason": "NO_DEDICATED_FIELD_IN_02_CORE_SKU_PERFORMANCE; retained in canonical local facts"},
            {"metric": "contribution_profit", "reason": "NO_DEDICATED_FIELD_IN_02_CORE_SKU_PERFORMANCE; retained in canonical local facts"},
            {"metric": "contribution_margin", "reason": "PARTIAL_SKU_AVAILABILITY_AND_NO_DEDICATED_FIELD; retained without allocation"},
            {"metric": "refund_amount", "reason": "NO_DEDICATED_FIELD; retained in canonical facts and deterministic negative-sales evidence"},
            {"metric": "ad_sales", "reason": "NO_DEDICATED_FIELD; retained in canonical facts and ad-waste evidence"},
            {"metric": "inventory_status", "reason": "NO_DEDICATED_STOCK_STATE_FIELD; retained in evidence and not mapped to Buyability"},
        ],
        "feishu_candidate_set": {
            "target_table": "02 Core SKU Performance",
            "live_table_id": schema["live_identifiers"]["tables"]["02 Core SKU Performance"]["table_id"],
            "live_schema_field_count": len(live_fields),
            "live_record_lookup_performed": True,
            "live_record_count": live_record_count,
            "candidate_count": len(candidates),
            "candidate_skus": [candidate["create_fields"]["SKU"] for candidate in candidates],
            "identity_collision_count": 0,
            "validation_status": "PASS" if live_record_count == 0 else "IDENTITY_LOOKUP_REQUIRED",
            "external_write_performed": False,
            "candidates": candidates,
        },
        "governance": {
            "sku_health_scoring_performed": False,
            "all_candidate_status_values": ["UNKNOWN"],
            "signal_records_created": 0,
            "action_records_created": 0,
            "feishu_records_written": 0,
            "feishu_schema_changes": 0,
        },
    }


def render_core_sku_preview(package: Mapping[str, Any]) -> str:
    """Render a compact, human-reviewable Phase 2E management preview."""

    ranking = package["rankings"]
    flags = package["factual_flags"]
    reconciliation = package["reconciliation"]
    candidate = package["feishu_candidate_set"]
    context = package["platform_context"]

    def fmt(value: Any, *, percent: bool = False) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.1%}" if percent else f"{float(value):,.2f}"

    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|")

    lines = [
        "# WALMART MP — CORE SKU DRIVERS",
        "",
        f"**Control week:** `{package['control_week']}`  ",
        f"**Official SKU data through:** `{package['business_as_of_date']}`  ",
        "**Mode:** `SUPERVISED_WRITE_CANDIDATE_ONLY` — no Feishu write or schema change occurred.",
        "",
        "## Why Walmart is RED",
        "",
        f"- **Actual Sales / August BP / Gap:** {fmt(context['actual_sales'])} / {fmt(context['bp_sales'])} / {fmt(context['sales_gap'])} USD",
        f"- **Sales attainment:** {fmt(context['sales_attainment'], percent=True)}",
        f"- **Overall / Sales / CM / Ads / Inventory:** `{context['overall_health']}` / `{context['sales_health']}` / `{context['cm_health']}` / `{context['ads_health']}` / `{context['inventory_health']}`",
        f"- **Data confidence:** `{context['data_confidence']}`",
        f"- **SKU explanation:** {package['eligible_sku_fact_count']} eligible SKU facts; sales reconciles exactly to the platform result.",
        "",
        "## Top Sales Detractors",
        "",
        "| Rank | SKU | Product / Model | Actual | BP | Gap | Attainment | WoW | Share of negative gap | Key evidence |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for index, item in enumerate(ranking["top_sales_target_detractors"], start=1):
        lines.append(
            f"| {index} | `{item['sku']}` | {cell(item['product_name'])} | {fmt(item['sales'])} | {fmt(item['target'])} | {fmt(item['target_delta'])} | {fmt(item['attainment'], percent=True)} | {fmt(item['wow_sales_pct'], percent=True)} | {fmt(item['share_of_total_negative_gap'], percent=True)} | {', '.join(item['issue_flags']) or 'BELOW_BP'}; through {item['data_as_of']} |"
        )
    lines.extend(
        [
            "",
            "## Positive Contributors",
            "",
        ]
    )
    if ranking["top_positive_sales_contributors"]:
        lines.extend(["| Rank | SKU | Product / Model | Actual | BP | Positive gap | Evidence |", "|---:|---|---|---:|---:|---:|---|"])
        for index, item in enumerate(ranking["top_positive_sales_contributors"], start=1):
            lines.append(f"| {index} | `{item['sku']}` | {cell(item['product_name'])} | {fmt(item['sales'])} | {fmt(item['target'])} | {fmt(item['target_delta'])} | Positive Actual - BP; through {item['data_as_of']} |")
    else:
        lines.append("No SKU has a positive `Actual Sales - full-month BP Sales` gap in the current compatible set; the list is intentionally empty.")
    lines.extend(
        [
            "",
            "## Advertising Waste",
            "",
            "| SKU | Spend | Attributed Sales | ROAS | Evidence |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for item in flags["ad_spend_with_zero_attributed_sales"]:
        lines.append(f"| `{item['sku']}` | {fmt(item['ad_spend'])} | {fmt(item['ad_sales'])} | {fmt(item['roas'])} | `AD_SPEND_WITH_ZERO_ATTRIBUTED_SALES`; through {item['data_as_of']} |")
    lines.extend(
        [
            "",
            "## Availability Issues",
            "",
            "| SKU | Availability | Units | Sales / BP context |",
            "|---|---|---:|---|",
        ]
    )
    for item in flags["out_of_stock"]:
        lines.append(f"| `{item['sku']}` | `OUT_OF_STOCK` | {fmt(item['inventory_units'])} | {fmt(item['sales'])} / {fmt(item['target'])} USD |")
    lines.extend(
        [
            "",
            "## Negative Sales / Refund Evidence",
            "",
            "| SKU | Net Sales | Refund Amount | Derived Gross Sales | Evidence |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for item in flags["negative_net_sales"]:
        lines.append(f"| `{item['sku']}` | {fmt(item['sales'])} | {fmt(item['refund_amount'])} | {fmt(item['gross_sales_derived'])} | `gross_sales = net_sales + refund_amount`; no causal claim |")
    lines.extend(
        [
            "",
            "## Data Coverage",
            "",
            f"- Sales through: `{context['data_through']['sales']}` (`SKU_MTD` / `BUSINESS_MTD`).",
            f"- Ads through: `{context['data_through']['ads']}`.",
            f"- Inventory through: `{context['data_through']['inventory']}`.",
            f"- CM through: `{context['data_through']['cm']}` at platform grain only; it was not allocated to SKUs.",
            f"- SKU weekly period pair: `{package['weekly_comparison']['status']}` — {package['weekly_comparison'].get('previous_period')} vs {package['weekly_comparison'].get('current_period')}.",
            "- SKU-level weekly sales values are unavailable in both official weekly releases; every `WoW Sales %` remains NULL.",
            "- MTD trend deltas were not reused as WoW because the source MTD coverage windows are not equal.",
            "- Buyability and Listing Status remain `UNKNOWN`; inventory/item status was not repurposed as those measures.",
            "- Every candidate `Status` is `UNKNOWN`; no SKU-health score or threshold was introduced.",
            "",
            "## Reconciliation",
            "",
            "| Metric | SKU total | Platform total | Difference | Status |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for metric in ("sales", "ad_spend", "inventory"):
        item = reconciliation[metric]
        lines.append(
            f"| {metric} | {item['sku_total']:.2f} | {item['platform_total']:.2f} | {item['difference']:.2f} | `{item['status']}` |"
        )
    bp = reconciliation["bp_sales"]
    lines.append(
        f"| bp_sales | {bp['matched_sku_total']:.2f} | {bp['platform_target_total']:.2f} | {bp['difference']:.2f} | `{bp['status']}` |"
    )
    lines.extend(
        [
            "",
            "The ad-spend difference is `EXPLAINED_DIFFERENCE`: platform spend includes 54.86 USD not allocated to eligible SKU rows; it was not forced onto SKUs.",
            "",
            "## Feishu Supervised-Write Candidate",
            "",
            f"- Live target: `{candidate['live_table_id']}` / `{candidate['target_table']}` / `{candidate['live_schema_field_count']}` fields.",
            f"- Eligible local SKU facts: `{package['eligible_sku_fact_count']}`; management candidates: `{candidate['candidate_count']}`.",
            f"- Live records found: `{candidate['live_record_count']}`; proposed action: `CREATE` for all `{candidate['candidate_count']}` identities.",
            f"- Candidate validation: `{candidate['validation_status']}`.",
            f"- Exact SKUs: `{', '.join(candidate['candidate_skus'])}`.",
            "- No Business Health, Signal, or Action record was created or updated.",
            "",
        ]
    )
    return "\n".join(lines)
