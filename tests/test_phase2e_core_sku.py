from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from storm.adapters.walmart_official import DatasetEvidence, WalmartOfficialEvidence
from storm.cockpit.core_sku import build_walmart_core_sku_package


SCHEMA = Path(__file__).parents[1] / "config" / "feishu_schema.yaml"


def _platform_health() -> dict:
    return {
        "control_week": "2026-W33",
        "market": "US",
        "platform": "WALMART_MP",
        "interpretation": {"overall_status": "RED", "sales_status": "RED", "cm_status": "RED", "ads_status": "RED", "inventory_status": "UNKNOWN", "data_confidence": "MEDIUM"},
        "facts": {
            "actual_sales": {"value": 10.0, "data_through_date": "2026-08-02", "source_release": "RUN-OFFICIAL"},
            "bp_sales": {"value": 50.0, "data_through_date": None},
            "actual_cm": {"value": -2.0, "data_through_date": "2026-08-02"},
            "bp_cm": {"value": 5.0, "data_through_date": None},
            "ad_spend": {"value": 5.0, "data_through_date": "2026-08-02"},
            "attributed_ad_sales": {"value": 0.0, "data_through_date": "2026-08-02"},
            "roas": {"value": 0.0, "data_through_date": "2026-08-02"},
            "inventory_units": {"value": 8.0, "data_through_date": "2026-08-02"},
        },
        "derived_control_metrics": {"sales_attainment_pct": {"value": 0.2}},
    }


def _dataset(name: str, records: list[dict], *, history: list[dict] | None = None) -> DatasetEvidence:
    return DatasetEvidence(
        dataset_name=name,
        source_artifact=f"{name}.fixture",
        source_release="RUN-OFFICIAL",
        schema_version="1.0.0",
        business_date="2026-08-02",
        readiness_status="READY",
        record_count=len(records),
        content_hash=f"HASH-{name}",
        records=tuple(records),
        history_records=tuple(history or ()),
    )


def _evidence(*, gapped_weekly: bool = False) -> WalmartOfficialEvidence:
    current = [
        {"sku": "A", "net_sales": 20.0, "orders": 2, "units_sold": 2, "contribution_profit": 4.0, "contribution_margin": 0.2, "refund_amount": 0.0, "refund_amount_rate": 0.0, "ad_spend": 5.0, "ad_sales": 0.0, "calculated_roas": 0.0, "inventory_units": 5.0, "inventory_status": "In Stock", "inventory_data_status": "AVAILABLE", "item_status": "ACTIVE", "fulfillment_type": "WFS", "period_scope": "MTD_OPERATING", "business_as_of_date": "2026-08-02", "coverage_start_date": "2026-08-01", "coverage_end_date": "2026-08-02", "metric_scope": "SKU_MTD", "source_run_id": "RUN-OFFICIAL", "snapshot_content_hash": "SKU-HASH", "created_at_utc": "2026-08-04T00:00:00Z"},
        {"sku": "B", "net_sales": -10.0, "orders": -1, "units_sold": -1, "contribution_profit": -2.0, "contribution_margin": None, "refund_amount": 10.0, "refund_amount_rate": None, "ad_spend": None, "ad_sales": None, "calculated_roas": None, "inventory_units": 0.0, "inventory_status": "Out of Stock", "inventory_data_status": "AVAILABLE", "item_status": "ACTIVE", "fulfillment_type": "WFS", "period_scope": "MTD_OPERATING", "business_as_of_date": "2026-08-02", "coverage_start_date": "2026-08-01", "coverage_end_date": "2026-08-02", "metric_scope": "SKU_MTD", "source_run_id": "RUN-OFFICIAL", "snapshot_content_hash": "SKU-HASH", "created_at_utc": "2026-08-04T00:00:00Z"},
        {"sku": "C", "net_sales": None, "orders": None, "units_sold": None, "contribution_profit": None, "contribution_margin": None, "refund_amount": None, "refund_amount_rate": None, "ad_spend": None, "ad_sales": None, "calculated_roas": None, "inventory_units": 3.0, "inventory_status": "In Stock", "inventory_data_status": "AVAILABLE", "item_status": "ACTIVE", "fulfillment_type": "Seller", "period_scope": "MTD_OPERATING", "business_as_of_date": "2026-08-02", "coverage_start_date": "2026-08-01", "coverage_end_date": "2026-08-02", "metric_scope": "SKU_MTD", "source_run_id": "RUN-OFFICIAL", "snapshot_content_hash": "SKU-HASH", "created_at_utc": "2026-08-04T00:00:00Z"},
    ]
    previous_start = "2026-07-19" if gapped_weekly else "2026-07-20"
    weekly_history: list[dict] = []
    for sku, previous, latest in (("A", 7.0, 14.0), ("B", 0.0, 2.0), ("C", 4.0, None)):
        weekly_history.extend(
            [
                {"sku": sku, "period_scope": "WEEKLY_OPERATING", "business_as_of_date": "2026-07-26", "coverage_start_date": previous_start, "coverage_end_date": "2026-07-26", "metric_scope": "SKU_WEEKLY", "weekly_sku_net_sales": previous, "weekly_sku_contribution_profit": None, "weekly_sku_refund_amount": None, "weekly_sku_margin": None, "weekly_sku_financial_status": "AVAILABLE", "weekly_ad_spend": None, "weekly_ad_sales": None, "weekly_impressions": None, "weekly_clicks": None, "weekly_calculated_roas": None, "source_run_id": "RUN-PREV", "snapshot_content_hash": "WEEK-PREV", "created_at_utc": "2026-07-28T00:00:00Z"},
                {"sku": sku, "period_scope": "WEEKLY_OPERATING", "business_as_of_date": "2026-08-02", "coverage_start_date": "2026-07-27", "coverage_end_date": "2026-08-02", "metric_scope": "SKU_WEEKLY", "weekly_sku_net_sales": latest, "weekly_sku_contribution_profit": None, "weekly_sku_refund_amount": None, "weekly_sku_margin": None, "weekly_sku_financial_status": "AVAILABLE", "weekly_ad_spend": None, "weekly_ad_sales": None, "weekly_impressions": None, "weekly_clicks": None, "weekly_calculated_roas": None, "source_run_id": "RUN-OFFICIAL", "snapshot_content_hash": "WEEK-CURRENT", "created_at_utc": "2026-08-04T00:00:00Z"},
            ]
        )
    attributes = [
        {"sku": "A", "item_id": "1", "product_name": "Alpha", "product_line": "Robotic Lawn Mowers", "product_subcategory": "Robot", "strategic_role": "Core", "channel": "3P", "fulfillment_type": "WFS", "item_status": "ACTIVE", "attribute_record_status": "ACTIVE", "last_review_date": "2026-07-01", "review_status": "CURRENT"},
        {"sku": "B", "item_id": "2", "product_name": "Beta", "product_line": "String Trimmers", "product_subcategory": "OPE", "strategic_role": "Growth", "channel": "3P", "fulfillment_type": "WFS", "item_status": "ACTIVE", "attribute_record_status": "ACTIVE", "last_review_date": "2026-07-01", "review_status": "CURRENT"},
        {"sku": "C", "item_id": "3", "product_name": "Gamma", "product_line": "Power Tool Batteries", "product_subcategory": "Accessory", "strategic_role": "Support/Accessory", "channel": "3P", "fulfillment_type": "Seller", "item_status": "ACTIVE", "attribute_record_status": "ACTIVE", "last_review_date": "2026-07-01", "review_status": "CURRENT"},
    ]
    business = [{"net_sales": 10.0, "ad_spend": 5.0, "inventory_units": 8.0}]
    return WalmartOfficialEvidence(
        source_system="Walmart Operation System",
        source_scope="WALMART_MARKETPLACE_3P",
        platform="WALMART_MP",
        official_run_id="RUN-OFFICIAL",
        release_version="1.1.1",
        contract_version="1.1.0",
        business_as_of_date="2026-08-02",
        generated_at_utc="2026-08-04T00:00:00Z",
        release_manifest="outputs/latest/backend_release_manifest.json",
        datasets={
            "business_current_state": _dataset("business_current_state", business),
            "sku_current_performance": _dataset("sku_current_performance", current),
            "sku_weekly_history": _dataset("sku_weekly_history", [row for row in weekly_history if row["business_as_of_date"] == "2026-08-02"], history=weekly_history),
            "sku_business_attributes": _dataset("sku_business_attributes", attributes),
        },
    )


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE FACT_BP_TARGET_MONTHLY (
            year INTEGER, month INTEGER, platform TEXT, canonical_sku TEXT,
            bp_units REAL, bp_sales REAL, import_batch_id TEXT,
            source_sheet TEXT, source_rows_json TEXT)"""
        )
        connection.executemany(
            "INSERT INTO FACT_BP_TARGET_MONTHLY VALUES (2026, 8, 'WALMART_MP', ?, ?, ?, 'BATCH-1', 'SKU BP', '[]')",
            [("A", 2.0, 30.0), ("B", 1.0, 20.0), ("C", 0.0, 0.0)],
        )


def test_phase2e_source_identity_null_rank_flags_reconciliation_and_candidate_mapping(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database)
    package = build_walmart_core_sku_package(
        _evidence(), database, SCHEMA, control_week="2026-W33", live_record_count=0,
        platform_health_snapshot=_platform_health(),
    )
    facts = {row["sku"]: row for row in package["eligible_sku_facts"]}
    assert package["source_release"]["official_run_id"] == "RUN-OFFICIAL"
    assert package["eligible_sku_fact_count"] == 3
    assert facts["A"]["wow_sales_pct"] == 1.0
    assert facts["B"]["wow_sales_pct"] is None
    assert facts["B"]["wow_unavailable_reason"] == "PRIOR_SKU_WEEKLY_SALES_ZERO"
    assert facts["C"]["sales"] is None
    assert facts["C"]["target_gap_pct"] is None
    assert facts["A"]["sku_role"] == "OTHER"
    assert facts["A"]["sku_role_mapping"] == "SOURCE_VALUE_NOT_IN_FEISHU_ENUM"
    assert facts["B"]["sku_role"] == "GROWTH"
    assert package["role_classification"]["inference_from_performance_performed"] is False
    assert package["rankings"]["top_sales_target_detractors"][0]["sku"] == "B"
    assert package["factual_flags"]["ad_spend_with_zero_attributed_sales"][0]["sku"] == "A"
    assert package["factual_flags"]["negative_net_sales"][0]["sku"] == "B"
    assert package["factual_flags"]["out_of_stock"][0]["sku"] == "B"
    assert package["reconciliation"]["sales"]["status"] == "PASS"
    assert package["reconciliation"]["bp_sales"]["status"] == "PASS"
    candidates = package["feishu_candidate_set"]
    assert candidates["candidate_count"] == 2
    assert candidates["validation_status"] == "PASS"
    assert all(item["action"] == "CREATE" for item in candidates["candidates"])
    assert all(item["create_fields"]["Status"] == "UNKNOWN" for item in candidates["candidates"])
    assert all(item["create_fields"]["Buyability"] == "UNKNOWN" for item in candidates["candidates"])
    assert all(item["create_fields"]["Listing Status"] == "UNKNOWN" for item in candidates["candidates"])
    assert all(item["identity"]["SKU Perf ID"].startswith("SKU-2026W33-US-WMT-") for item in candidates["candidates"])
    assert package["governance"]["sku_health_scoring_performed"] is False
    assert package["governance"]["feishu_records_written"] == 0
    json.dumps(package)


def test_phase2e_gapped_weekly_periods_are_not_compared(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database)
    package = build_walmart_core_sku_package(
        _evidence(gapped_weekly=True), database, SCHEMA, control_week="2026-W33", live_record_count=0,
        platform_health_snapshot=_platform_health(),
    )
    assert package["weekly_comparison"]["status"] == "UNAVAILABLE"
    assert package["weekly_comparison"]["reason"] == "SKU_WEEKLY_PERIODS_NOT_EQUAL_LENGTH_AND_CONSECUTIVE"
    assert all(row["wow_sales_pct"] is None for row in package["eligible_sku_facts"])
