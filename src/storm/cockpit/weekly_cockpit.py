"""Phase 2F deterministic Managed SKU scope and weekly cockpit artifact."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from storm.domain.ids import mint_sku_id


class WeeklyCockpitBuildError(RuntimeError):
    """Raised when a Phase 2F selection, schema, or source gate fails."""


ROLE_MAP = {
    "Core": "CORE",
    "Growth": "GROWTH",
    "Profit": "PROFIT",
    "Support/Accessory": "SUPPORT_ACCESSORY",
}


def _ranked_skus(rows: list[Mapping[str, Any]], *, count: int | None = None) -> list[str]:
    values = [str(row["sku"]) for row in rows]
    return values if count is None else values[:count]


def _selection(phase2e: Mapping[str, Any]) -> dict[str, Any]:
    facts = phase2e["eligible_sku_facts"]
    by_sku = {str(row["sku"]): row for row in facts}
    if len(by_sku) != int(phase2e["eligible_sku_fact_count"]):
        raise WeeklyCockpitBuildError("PHASE2E_SKU_IDENTITY_DUPLICATE")
    strategic_eligible = sorted(
        sku
        for sku, fact in by_sku.items()
        if fact["strategic_role_raw"] in {"Core", "Growth", "Profit"}
    )
    core = sorted(
        sku for sku, fact in by_sku.items() if fact["strategic_role_raw"] == "Core"
    )
    detractors = _ranked_skus(phase2e["rankings"]["top_sales_target_detractors"], count=5)
    positive = _ranked_skus(phase2e["rankings"]["top_positive_sales_contributors"], count=3)
    ad_waste = [
        str(row["sku"])
        for row in sorted(
            phase2e["factual_flags"]["ad_spend_with_zero_attributed_sales"],
            key=lambda row: (-float(row["ad_spend"]), str(row["sku"])),
        )[:3]
    ]
    material_oos_rows = sorted(
        (
            row
            for row in phase2e["factual_flags"]["out_of_stock"]
            if row.get("target") is not None and float(row["target"]) > 0
        ),
        key=lambda row: (-float(row["target"]), str(row["sku"])),
    )[:3]
    material_oos = [str(row["sku"]) for row in material_oos_rows]
    managed = sorted(set(core + detractors + positive + ad_waste + material_oos))
    cockpit = []
    for sku in detractors + positive + ad_waste + material_oos:
        if sku not in cockpit:
            cockpit.append(sku)
    reasons: dict[str, list[str]] = {sku: [] for sku in managed}
    for sku in core:
        reasons[sku].append("STRATEGIC_CORE")
    for sku in detractors:
        reasons[sku].extend(["TOP_5_SALES_DETRACTOR", "BELOW_BP"])
    for sku in positive:
        reasons[sku].append("POSITIVE_CONTRIBUTOR")
    for sku in ad_waste:
        reasons[sku].append("MATERIAL_AD_SPEND_WITH_ZERO_ATTRIBUTED_SALES")
    for sku in material_oos:
        reasons[sku].append("BP_MATERIAL_OUT_OF_STOCK")
    if not (10 <= len(managed) <= 15):
        raise WeeklyCockpitBuildError(f"MANAGED_SKU_SCOPE_NOT_PRACTICAL: {len(managed)}")
    if not set(cockpit).issubset(managed):
        raise WeeklyCockpitBuildError("COCKPIT_DRIVER_OUTSIDE_MANAGED_SCOPE")
    return {
        "all_fact_count": len(facts),
        "strategic_eligible_count": len(strategic_eligible),
        "strategic_eligible_skus": strategic_eligible,
        "managed_skus": managed,
        "cockpit_driver_skus": cockpit,
        "selection_reasons": reasons,
        "components": {
            "all_core": core,
            "top_5_sales_detractors": detractors,
            "positive_contributors_up_to_3": positive,
            "top_3_ad_waste_by_spend": ad_waste,
            "top_3_oos_by_positive_bp": material_oos,
        },
    }


def _schema(schema_path: str | Path) -> tuple[dict[str, Any], dict[str, str]]:
    schema = yaml.safe_load(Path(schema_path).read_text(encoding="utf-8"))
    table = next(item for item in schema["tables"] if item["name"] == "02 Core SKU Performance")
    role = next(item for item in table["fields"] if item["name"] == "SKU Role")
    required_roles = {"CORE", "GROWTH", "PROFIT", "SUPPORT_ACCESSORY"}
    if not required_roles.issubset(set(role["options"])):
        raise WeeklyCockpitBuildError("CANONICAL_ROLE_TAXONOMY_INCOMPLETE")
    live = schema["live_identifiers"]["tables"]["02 Core SKU Performance"]
    fields = {str(name): str(field_id) for name, field_id in live["fields"].items()}
    if {item["name"] for item in table["fields"]} != set(fields):
        raise WeeklyCockpitBuildError("CORE_SKU_LIVE_MANIFEST_FIELD_DRIFT")
    return table, fields


def _candidate_fields(
    fact: Mapping[str, Any],
    *,
    control_week: str,
    reasons: list[str],
    source_release: str,
    target_batch: str,
) -> dict[str, Any]:
    raw_role = str(fact["strategic_role_raw"])
    if raw_role not in ROLE_MAP:
        raise WeeklyCockpitBuildError(f"AUTHORITATIVE_ROLE_UNMAPPED: {raw_role}")
    change_parts: list[str] = []
    if fact.get("target_delta") is not None:
        change_parts.append(
            f"MTD sales minus full-month BP: {float(fact['target_delta']):.2f} USD"
        )
    if fact["flags"]["negative_net_sales"]:
        change_parts.append(f"Negative MTD net sales: {float(fact['sales']):.2f} USD")
    if fact["flags"]["ad_spend_with_zero_attributed_sales"]:
        change_parts.append(
            f"Ad spend {float(fact['ad_spend']):.2f} USD with attributed sales 0.00 USD"
        )
    if fact["flags"]["out_of_stock"]:
        change_parts.append("Official inventory status: Out of Stock")
    if not change_parts:
        change_parts.append(f"Authoritative strategic role: {raw_role}")
    values: dict[str, Any] = {
        "SKU Perf ID": mint_sku_id(control_week, "US", "WMT", str(fact["sku"])),
        "Week": control_week,
        "Market": "US",
        "Platform": "Walmart",
        "Channel": "3P",
        "Product Line": fact["product_line"],
        "SKU": fact["sku"],
        "Model / Product": fact["product_name"],
        "SKU Role": ROLE_MAP[raw_role],
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
        "Diagnosis": ", ".join(reasons),
        "Data As Of": fact["data_as_of"],
        "Source Type": "MIXED",
        "Source Ref": (
            f"Walmart official run {source_release}; governed SKU attributes; "
            f"STORM BP {target_batch}"
        ),
        "Evidence": (
            f"SKU_MTD {fact['coverage_start_date']} to {fact['coverage_end_date']}; "
            f"authoritative role {raw_role}; selection {', '.join(reasons)}"
        ),
        "Human Reviewed": False,
        "Snapshot Locked": False,
    }
    return {name: value for name, value in values.items() if value is not None}


def build_phase2f_package(
    phase2e: Mapping[str, Any],
    business_health: Mapping[str, Any],
    schema_path: str | Path,
    *,
    live_record_count: int,
) -> dict[str, Any]:
    """Build Phase 2F scope, candidates, and cockpit data without live mutation."""

    control_week = str(phase2e["control_week"])
    if business_health.get("control_week") != control_week:
        raise WeeklyCockpitBuildError("BUSINESS_HEALTH_CONTROL_WEEK_MISMATCH")
    selection = _selection(phase2e)
    table, live_fields = _schema(schema_path)
    field_specs = {item["name"]: item for item in table["fields"]}
    facts = {str(row["sku"]): row for row in phase2e["eligible_sku_facts"]}
    target_batches = sorted(
        {
            str(candidate["create_fields"]["Source Ref"]).split("STORM BP ", 1)[-1]
            for candidate in phase2e["feishu_candidate_set"]["candidates"]
            if "STORM BP " in str(candidate["create_fields"].get("Source Ref"))
        }
    )
    if len(target_batches) != 1:
        raise WeeklyCockpitBuildError("TARGET_BATCH_LINEAGE_AMBIGUOUS")
    candidates: list[dict[str, Any]] = []
    identities: set[str] = set()
    for sku in selection["managed_skus"]:
        fields = _candidate_fields(
            facts[sku],
            control_week=control_week,
            reasons=selection["selection_reasons"][sku],
            source_release=str(phase2e["source_release"]["official_run_id"]),
            target_batch=target_batches[0],
        )
        required = {name for name, spec in field_specs.items() if spec.get("required")}
        missing = sorted(required - set(fields))
        if missing:
            raise WeeklyCockpitBuildError(f"MANAGED_CANDIDATE_REQUIRED_FIELDS_MISSING: {sku}: {missing}")
        for name, value in fields.items():
            options = field_specs[name].get("options")
            if options and value not in options:
                raise WeeklyCockpitBuildError(f"MANAGED_CANDIDATE_ENUM_INVALID: {sku}: {name}: {value}")
        identity = str(fields["SKU Perf ID"])
        if identity in identities:
            raise WeeklyCockpitBuildError(f"MANAGED_CANDIDATE_IDENTITY_DUPLICATE: {identity}")
        identities.add(identity)
        candidates.append(
            {
                "action": "CREATE" if live_record_count == 0 else "REQUIRES_IDENTITY_LOOKUP",
                "identity": identity,
                "sku": sku,
                "selection_reasons": selection["selection_reasons"][sku],
                "fields": fields,
                "fields_by_live_id": {live_fields[name]: value for name, value in fields.items()},
            }
        )

    interpretation = business_health["interpretation"]
    health_facts = business_health["facts"]
    derived = business_health["derived_control_metrics"]
    weekly = derived["weekly_sales_change"]["value"]
    if not weekly or weekly.get("availability") != "AVAILABLE":
        raise WeeklyCockpitBuildError("COMPARABLE_BUSINESS_WEEKLY_TREND_UNAVAILABLE")
    platform = {
        "platform": "WALMART MP",
        "control_week": control_week,
        "overall_health": interpretation["overall_status"],
        "data_confidence": interpretation["data_confidence"],
        "actual_sales": health_facts["actual_sales"]["value"],
        "bp_sales": health_facts["bp_sales"]["value"],
        "sales_attainment": derived["sales_attainment_pct"]["value"],
        "sales_gap": health_facts["actual_sales"]["value"] - health_facts["bp_sales"]["value"],
        "actual_cm": health_facts["actual_cm"]["value"],
        "bp_cm": health_facts["bp_cm"]["value"],
        "cm_attainment": derived["cm_attainment_pct"]["value"],
        "cm_pct": derived["actual_cm_pct"]["value"],
        "ad_spend": health_facts["ad_spend"]["value"],
        "ad_sales": health_facts["attributed_ad_sales"]["value"],
        "roas": health_facts["roas"]["value"],
        "inventory_units": health_facts["inventory_units"]["value"],
        "oos_sku_count": len(phase2e["factual_flags"]["out_of_stock"]),
        "weekly_change": weekly["absolute_change"],
        "weekly_change_pct": weekly["percent_change"],
        "data_through": {
            "sales": health_facts["actual_sales"]["data_through_date"],
            "cm": health_facts["actual_cm"]["data_through_date"],
            "ads": health_facts["ad_spend"]["data_through_date"],
            "inventory": health_facts["inventory_units"]["data_through_date"],
            "ytd": health_facts["ytd_actual_cm"]["availability"],
        },
    }
    trend = [
        {
            "period": "Jul 20–26",
            "period_order": 1,
            "weekly_sales": weekly["previous_value"],
            "period_type": "WEEKLY_OPERATING",
        },
        {
            "period": "Jul 27–Aug 2",
            "period_order": 2,
            "weekly_sales": weekly["current_value"],
            "period_type": "WEEKLY_OPERATING",
        },
    ]
    detractor_by_sku = {
        str(row["sku"]): row for row in phase2e["rankings"]["top_sales_target_detractors"]
    }
    driver_rows: list[dict[str, Any]] = []
    for rank, sku in enumerate(selection["components"]["top_5_sales_detractors"], start=1):
        row = detractor_by_sku[sku]
        evidence_tags = ["BELOW_BP"]
        if facts[sku]["flags"]["negative_net_sales"]:
            evidence_tags.append("NEGATIVE_NET_SALES")
        if facts[sku]["flags"]["ad_spend_with_zero_attributed_sales"]:
            evidence_tags.append("AD_WASTE")
        driver_rows.append(
            {
                "rank": rank,
                "sku": sku,
                "role": ROLE_MAP[str(facts[sku]["strategic_role_raw"])],
                "actual": row["sales"],
                "bp": row["target"],
                "gap": row["target_delta"],
                "attainment": row["attainment"],
                "evidence": ", ".join(evidence_tags),
            }
        )
    attention = {
        "positive": [
            {
                "sku": sku,
                "role": ROLE_MAP[str(facts[sku]["strategic_role_raw"])],
                "actual": facts[sku]["sales"],
                "bp": facts[sku]["target"],
                "gap": facts[sku]["target_delta"],
                "evidence": "POSITIVE_CONTRIBUTOR",
            }
            for sku in selection["components"]["positive_contributors_up_to_3"]
        ],
        "ad_waste": [
            {
                "sku": sku,
                "role": ROLE_MAP[str(facts[sku]["strategic_role_raw"])],
                "ad_spend": facts[sku]["ad_spend"],
                "ad_sales": facts[sku]["ad_sales"],
                "roas": facts[sku]["roas"],
                "evidence": "AD_SPEND_WITH_ZERO_ATTRIBUTED_SALES",
            }
            for sku in selection["components"]["top_3_ad_waste_by_spend"]
        ],
        "material_oos": [
            {
                "sku": sku,
                "role": ROLE_MAP[str(facts[sku]["strategic_role_raw"])],
                "inventory": facts[sku]["inventory"],
                "bp": facts[sku]["target"],
                "actual": facts[sku]["sales"],
                "evidence": "BP_MATERIAL_OUT_OF_STOCK",
            }
            for sku in selection["components"]["top_3_oos_by_positive_bp"]
        ],
    }
    return {
        "schema_version": "1.0.0",
        "phase": "PHASE_2F",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection": selection,
        "role_taxonomy": {
            "authoritative_values": list(ROLE_MAP),
            "canonical_values": list(ROLE_MAP.values()),
            "existing_options_preserved": True,
            "live_extension_required": ["CORE", "SUPPORT_ACCESSORY"],
        },
        "feishu_candidate_set": {
            "target_table": "02 Core SKU Performance",
            "target_table_id": schema_path and yaml.safe_load(Path(schema_path).read_text(encoding="utf-8"))["live_identifiers"]["tables"]["02 Core SKU Performance"]["table_id"],
            "live_record_count_before": live_record_count,
            "candidate_count": len(candidates),
            "candidate_skus": [row["sku"] for row in candidates],
            "candidate_identities": [row["identity"] for row in candidates],
            "expected_behavior": "CREATE" if live_record_count == 0 else "REQUIRES_IDENTITY_LOOKUP",
            "external_write_performed": False,
            "candidates": candidates,
        },
        "cockpit": {
            "platform": platform,
            "weekly_trend": trend,
            "top_detractors": driver_rows,
            "attention": attention,
            "driver_skus": selection["cockpit_driver_skus"],
        },
        "governance": {
            "health_score_created": False,
            "signal_records_created": 0,
            "action_records_created": 0,
            "autonomous_recommendations_created": 0,
            "sku_records_written": 0,
        },
    }


def build_dashboard_artifact(package: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical portable dashboard artifact from reviewed Phase 2F data."""

    cockpit = package["cockpit"]
    platform = cockpit["platform"]
    platform_row = {
        key: value for key, value in platform.items() if key != "data_through"
    }
    platform_row.update(
        {
            "sales_through": platform["data_through"]["sales"],
            "cm_through": platform["data_through"]["cm"],
            "ads_through": platform["data_through"]["ads"],
            "inventory_through": platform["data_through"]["inventory"],
            "ytd_status": platform["data_through"]["ytd"],
        }
    )
    generated = str(package["generated_at_utc"])
    health_source = {
        "id": "business_health_snapshot",
        "label": "Accepted Walmart Business Health snapshot",
        "path": "data/cockpit/phase2c/walmart_business_health_snapshot_v3.json",
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "sql": "SELECT * FROM read_json_auto('data/cockpit/phase2c/walmart_business_health_snapshot_v3.json')",
            "description": "Read the accepted Phase 2C Walmart Business Health snapshot used for platform KPIs and comparable weekly sales.",
            "executed_at": generated,
            "tables_used": ["data/cockpit/phase2c/walmart_business_health_snapshot_v3.json"],
            "filters": ["control_week = 2026-W33", "platform = WALMART_MP"],
            "metric_definitions": {
                "sales_attainment": "MTD Actual Sales divided by full-month BP Sales.",
                "sales_gap": "MTD Actual Sales minus full-month BP Sales.",
                "cm_attainment": "MTD Actual CM divided by full-month BP CM.",
                "cm_pct": "Actual CM divided by CM-basis sales from the same accepted batch.",
            },
        },
    }
    sku_source = {
        "id": "weekly_driver_package",
        "label": "Accepted Walmart weekly SKU driver package",
        "path": "data/cockpit/phase2e/walmart_weekly_driver_package.json",
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "sql": "SELECT * FROM read_json_auto('data/cockpit/phase2e/walmart_weekly_driver_package.json')",
            "description": "Read the accepted Phase 2E SKU facts, rankings, factual flags, and reconciliations.",
            "executed_at": generated,
            "tables_used": ["data/cockpit/phase2e/walmart_weekly_driver_package.json"],
            "filters": ["control_week = 2026-W33", "platform = WALMART_MP", "official non-superseded release only"],
            "metric_definitions": {
                "top_detractors": "Five most negative comparable MTD Actual Sales minus full-month BP Sales gaps.",
                "ad_waste": "Ad Spend greater than zero with Attributed Sales equal to zero, ranked by spend.",
                "material_oos": "Out-of-stock SKUs ranked by positive full-month BP Sales.",
            },
        },
    }
    cards = [
        ("actual_sales", "Actual Sales", "actual_sales", "currency", "business_health_snapshot"),
        ("bp_sales", "BP", "bp_sales", "currency", "business_health_snapshot"),
        ("sales_attainment", "Attainment", "sales_attainment", "percent", "business_health_snapshot"),
        ("sales_gap", "Gap to BP", "sales_gap", "currency", "business_health_snapshot"),
        ("actual_cm", "Actual CM", "actual_cm", "currency", "business_health_snapshot"),
        ("bp_cm", "BP CM", "bp_cm", "currency", "business_health_snapshot"),
        ("cm_attainment", "CM Attainment", "cm_attainment", "percent", "business_health_snapshot"),
        ("cm_pct", "CM%", "cm_pct", "percent", "business_health_snapshot"),
        ("ad_spend", "Ad Spend", "ad_spend", "currency", "business_health_snapshot"),
        ("ad_sales", "Ad Sales", "ad_sales", "currency", "business_health_snapshot"),
        ("roas", "ROAS", "roas", "number", "business_health_snapshot"),
        ("inventory_units", "Inventory Units", "inventory_units", "number", "business_health_snapshot"),
        ("oos_sku_count", "OOS SKUs", "oos_sku_count", "number", "weekly_driver_package"),
    ]
    manifest_cards = [
        {
            "id": card_id,
            "description": f"{label} for Walmart MP in the current reviewed control context.",
            "dataset": "platform",
            "sourceId": source_id,
            "metrics": [{"label": label, "field": field, "format": fmt}],
        }
        for card_id, label, field, fmt, source_id in cards
    ]
    tables = [
        {
            "id": "top_detractors",
            "title": "Top Sales Detractors",
            "subtitle": "Largest current MTD sales gaps versus full-month BP.",
            "dataset": "top_detractors",
            "sourceId": "weekly_driver_package",
            "defaultSort": {"field": "rank", "direction": "asc"},
            "density": "dense",
            "layout": "full",
            "columns": [
                {"field": "rank", "label": "Rank", "format": "number"},
                {"field": "sku", "label": "SKU", "type": "text"},
                {"field": "role", "label": "Role", "type": "text"},
                {"field": "actual", "label": "Actual", "format": "currency"},
                {"field": "bp", "label": "BP", "format": "currency"},
                {"field": "gap", "label": "Gap", "format": "currency", "movement": True},
                {"field": "evidence", "label": "Key Evidence", "type": "text"},
            ],
        },
        {
            "id": "positive_contributors",
            "title": "Positive Contributors",
            "dataset": "positive",
            "sourceId": "weekly_driver_package",
            "defaultSort": {"field": "gap", "direction": "desc"},
            "density": "dense",
            "columns": [
                {"field": "sku", "label": "SKU", "type": "text"},
                {"field": "role", "label": "Role", "type": "text"},
                {"field": "actual", "label": "Actual", "format": "currency"},
                {"field": "bp", "label": "BP", "format": "currency"},
                {"field": "gap", "label": "Gap", "format": "currency", "movement": True},
            ],
        },
        {
            "id": "ad_waste",
            "title": "Advertising Waste",
            "dataset": "ad_waste",
            "sourceId": "weekly_driver_package",
            "defaultSort": {"field": "ad_spend", "direction": "desc"},
            "density": "dense",
            "columns": [
                {"field": "sku", "label": "SKU", "type": "text"},
                {"field": "role", "label": "Role", "type": "text"},
                {"field": "ad_spend", "label": "Ad Spend", "format": "currency"},
                {"field": "ad_sales", "label": "Ad Sales", "format": "currency"},
                {"field": "roas", "label": "ROAS", "format": "number"},
            ],
        },
        {
            "id": "material_oos",
            "title": "Material Availability Issues",
            "dataset": "material_oos",
            "sourceId": "weekly_driver_package",
            "defaultSort": {"field": "bp", "direction": "desc"},
            "density": "dense",
            "columns": [
                {"field": "sku", "label": "SKU", "type": "text"},
                {"field": "role", "label": "Role", "type": "text"},
                {"field": "inventory", "label": "Inventory", "format": "number"},
                {"field": "actual", "label": "Actual", "format": "currency"},
                {"field": "bp", "label": "BP", "format": "currency"},
            ],
        },
    ]
    attention_lines = ["## Other Attention", "", "### Positive Contributors"]
    for row in cockpit["attention"]["positive"]:
        attention_lines.append(
            f"- `{row['sku']}` · `{row['role']}` · Gap **${float(row['gap']):,.2f}**"
        )
    attention_lines.extend(["", "### Advertising Waste"])
    for row in cockpit["attention"]["ad_waste"]:
        attention_lines.append(
            f"- `{row['sku']}` · Spend **${float(row['ad_spend']):,.2f}** · Ad Sales **$0.00**"
        )
    attention_lines.extend(["", "### Material Availability"])
    for row in cockpit["attention"]["material_oos"]:
        attention_lines.append(
            f"- `{row['sku']}` · `OUT_OF_STOCK` · BP **${float(row['bp']):,.2f}**"
        )
    driver_lines = [
        "## Top Sales Detractors",
        "",
        "| Rank | SKU | Role | Actual | BP | Gap | Key Evidence |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in cockpit["top_detractors"]:
        driver_lines.append(
            f"| {row['rank']} | `{row['sku']}` | `{row['role']}` | ${float(row['actual']):,.2f} | ${float(row['bp']):,.2f} | ${float(row['gap']):,.2f} | {row['evidence']} |"
        )
    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "WALMART MP — Weekly Cockpit",
            "description": "Management cockpit for the current STORM weekly business review.",
            "generatedAt": generated,
            "cards": manifest_cards,
            "charts": [
                {
                    "id": "weekly_sales_comparison",
                    "title": "Comparable Weekly Sales",
                    "subtitle": f"Equal seven-day WEEKLY_OPERATING periods; change {platform['weekly_change']:.2f} USD ({platform['weekly_change_pct']:.1%}).",
                    "type": "bar",
                    "dataset": "weekly_trend",
                    "sourceId": "business_health_snapshot",
                    "encodings": {
                        "x": {"field": "period", "type": "ordinal", "label": "Comparable period"},
                        "y": {"field": "weekly_sales", "type": "quantitative", "label": "Weekly Sales", "format": "currency"},
                    },
                    "yAxisTitle": "Weekly Sales",
                    "valueFormat": "currency",
                    "layout": "full",
                }
            ],
            "tables": [],
            "sources": [health_source, sku_source],
            "blocks": [
                {
                    "id": "status",
                    "type": "markdown",
                    "sourceId": "business_health_snapshot",
                    "body": f"## WALMART MP\n\n**Control Week:** `{platform['control_week']}` · **Overall Health:** `{platform['overall_health']}` · **Data Confidence:** `{platform['data_confidence']}`",
                },
                {"id": "kpis", "type": "metric-strip", "cardIds": [item[0] for item in cards]},
                {"id": "trend", "type": "chart", "chartId": "weekly_sales_comparison", "layout": "full"},
                {
                    "id": "drivers",
                    "type": "markdown",
                    "sourceId": "weekly_driver_package",
                    "body": "\n".join(driver_lines),
                },
                {
                    "id": "attention",
                    "type": "markdown",
                    "sourceId": "weekly_driver_package",
                    "body": "\n".join(attention_lines),
                },
                {
                    "id": "coverage",
                    "type": "markdown",
                    "sourceId": "business_health_snapshot",
                    "body": (
                        "## Data Coverage\n\n"
                        f"Sales through **{platform['data_through']['sales']}** · "
                        f"CM through **{platform['data_through']['cm']}** · "
                        f"Ads through **{platform['data_through']['ads']}** · "
                        f"Inventory through **{platform['data_through']['inventory']}** · "
                        f"YTD CM **{platform['data_through']['ytd']}**"
                    ),
                },
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated,
            "status": "ready",
            "datasets": {
                "platform": [platform_row],
                "weekly_trend": cockpit["weekly_trend"],
                "top_detractors": cockpit["top_detractors"],
                "positive": cockpit["attention"]["positive"],
                "ad_waste": cockpit["attention"]["ad_waste"],
                "material_oos": cockpit["attention"]["material_oos"],
            },
        },
        "sources": [health_source, sku_source],
        "package_info": {
            "root": "data/cockpit/phase2f",
            "manifestPath": "walmart_weekly_cockpit_artifact.json",
            "snapshotPath": "walmart_weekly_cockpit_artifact.json",
        },
    }


def render_weekly_preview(package: Mapping[str, Any]) -> str:
    """Render a compact Markdown preview aligned to the cockpit hierarchy."""

    cockpit = package["cockpit"]
    p = cockpit["platform"]

    def money(value: Any) -> str:
        return f"${float(value):,.2f}"

    lines = [
        "# WALMART MP — WEEKLY COCKPIT",
        "",
        f"**Control Week:** `{p['control_week']}`  ",
        f"**Overall Health:** `{p['overall_health']}`  ",
        f"**Data Confidence:** `{p['data_confidence']}`",
        "",
        "## Performance",
        "",
        f"- Actual Sales / BP / Gap: **{money(p['actual_sales'])} / {money(p['bp_sales'])} / {money(p['sales_gap'])}**",
        f"- Sales Attainment: **{p['sales_attainment']:.2%}**",
        f"- Actual CM / BP CM: **{money(p['actual_cm'])} / {money(p['bp_cm'])}**",
        f"- CM Attainment / CM%: **{p['cm_attainment']:.2%} / {p['cm_pct']:.2%}**",
        f"- Ad Spend / Ad Sales / ROAS: **{money(p['ad_spend'])} / {money(p['ad_sales'])} / {p['roas']:.2f}**",
        f"- Inventory Units / OOS SKUs: **{p['inventory_units']:,.0f} / {p['oos_sku_count']}**",
        "",
        "## Comparable Weekly Change",
        "",
        f"- Previous: **{money(cockpit['weekly_trend'][0]['weekly_sales'])}** ({cockpit['weekly_trend'][0]['period']})",
        f"- Current: **{money(cockpit['weekly_trend'][1]['weekly_sales'])}** ({cockpit['weekly_trend'][1]['period']})",
        f"- Change: **{money(p['weekly_change'])} ({p['weekly_change_pct']:.2%})**",
        "",
        "## Top Sales Detractors",
        "",
        "| Rank | SKU | Role | Actual | BP | Gap | Key Evidence |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in cockpit["top_detractors"]:
        lines.append(f"| {row['rank']} | `{row['sku']}` | `{row['role']}` | {money(row['actual'])} | {money(row['bp'])} | {money(row['gap'])} | {row['evidence']} |")
    lines.extend(["", "## Other Attention", ""])
    for row in cockpit["attention"]["positive"]:
        lines.append(f"- Positive contributor: `{row['sku']}` — gap {money(row['gap'])}.")
    for row in cockpit["attention"]["ad_waste"]:
        lines.append(f"- Ad waste: `{row['sku']}` — spend {money(row['ad_spend'])}, attributed sales {money(row['ad_sales'])}.")
    for row in cockpit["attention"]["material_oos"]:
        lines.append(f"- Material OOS: `{row['sku']}` — BP {money(row['bp'])}, inventory {row['inventory'] or 0:,.0f}.")
    lines.extend(
        [
            "",
            "## Data Coverage",
            "",
            f"Sales through `{p['data_through']['sales']}` · CM through `{p['data_through']['cm']}` · Ads through `{p['data_through']['ads']}` · Inventory through `{p['data_through']['inventory']}` · YTD CM `{p['data_through']['ytd']}`.",
            "",
            "No autonomous recommendation, Signal, or Action is included.",
            "",
        ]
    )
    return "\n".join(lines)
