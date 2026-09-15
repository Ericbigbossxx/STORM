from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from storm.adapters.walmart_official import DatasetEvidence, WalmartOfficialEvidence
from storm.cockpit.business_health import BusinessHealthAssembler, compare_equal_weekly
from storm.cockpit.feishu_dry_run import build_feishu_dry_run, render_preview_v2
from storm.structured_metrics.schema import DDL


def _database(path: Path, *, bp_sales: float | None = 200.0) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(DDL)
        connection.execute(
            "INSERT INTO IMPORT_BATCH VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("BATCH-1", "cm.xlsx", "HASH-1", "OFFICIAL_CM_WORKBOOK", "2026-08|MTD",
             "2026-08-11", "2026-08-10", "2026-08-11T01:00:00+00:00", 3, 3, 0,
             "{}", "[]", "PASS", "COMMITTED"),
        )
        connection.execute(
            "INSERT INTO DIM_SKU VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("WALMART_MP", "SKU1", "SKU1", "Sunseeker", "Robot", None, "SELLER", "TTL amount", 1, "BATCH-1", "SKU Mapping", 1, ),
        )
        connection.execute(
            """INSERT INTO FACT_BP_TARGET_MONTHLY
               (year,month,platform,canonical_sku,bp_units,bp_sales,bp_cm,bp_cm_pct,import_batch_id,source_sheet,source_rows_json)
               VALUES (2026,8,'WALMART_MP','SKU1',10,?,20,0.1,'BATCH-1','KPI Rawdata','[1]')""",
            (bp_sales,),
        )
        connection.execute(
            """INSERT INTO FACT_CM_SNAPSHOT
               (snapshot_date,data_through_date,period_type,platform,brand,power_source,actual_units,actual_sales,
                actual_gm,actual_gm_pct,actual_cm,actual_cm_pct,bp_units,bp_sales,bp_cm,bp_cm_pct,cm_basis,
                primary_sales_basis,import_batch_id,source_sheet,source_range)
               VALUES ('2026-08-11','2026-08-10','MTD','WALMART_MP','Sunseeker','Robot',2,50,10,0.2,-5,-0.1,
                       10,200,20,0.1,'Contribution Margin','TTL amount','BATCH-1','Overview','A1:B2')"""
        )


def _walmart(*, net_sales: float = 25.0) -> WalmartOfficialEvidence:
    mtd = DatasetEvidence(
        "business_current_state", "business_mtd.parquet", "RUN-1", "1.0.0", "2026-08-02", "READY", 1, "HM",
        ({"period_scope": "MTD_OPERATING", "business_as_of_date": "2026-08-02", "coverage_start_date": "2026-08-01",
          "coverage_end_date": "2026-08-02", "net_sales": net_sales, "ad_spend": 5.0, "ad_sales": 10.0,
          "calculated_roas": 2.0, "inventory_units": 12},),
    )
    weekly_history = (
        {"period_scope": "WEEKLY_OPERATING", "business_as_of_date": "2026-07-26", "coverage_start_date": "2026-07-20", "coverage_end_date": "2026-07-26", "net_sales": 100.0},
        {"period_scope": "WEEKLY_OPERATING", "business_as_of_date": "2026-08-02", "coverage_start_date": "2026-07-27", "coverage_end_date": "2026-08-02", "net_sales": 75.0},
    )
    weekly = DatasetEvidence("business_weekly_current_state", "weekly.parquet", "RUN-1", "1.0.0", "2026-08-02", "READY", 1, "HW", (weekly_history[-1],), weekly_history)
    sku = DatasetEvidence(
        "sku_current_performance", "sku.parquet", "RUN-1", "1.0.0", "2026-08-02", "READY", 3, "HS",
        ({"inventory_status": "In Stock"}, {"inventory_status": "Out of Stock"}, {"inventory_status": None}),
    )
    manifest = DatasetEvidence("snapshot_manifest", "manifest.parquet", "RUN-1", "1.0.0", "2026-08-02", "READY", 3, "HX", ())
    return WalmartOfficialEvidence(
        "Walmart Operation System", "WALMART_MARKETPLACE_3P", "WALMART_MP", "RUN-1", "1.1.1", "1.1.0",
        "2026-08-02", "2026-08-04T00:00:00+00:00", "outputs/latest/backend_release_manifest.json",
        {"business_current_state": mtd, "business_weekly_current_state": weekly, "sku_current_performance": sku, "snapshot_manifest": manifest},
    )


def test_weekly_comparison_accepts_equal_consecutive_windows() -> None:
    result = compare_equal_weekly(_walmart().datasets["business_weekly_current_state"].history_records)
    assert result["availability"] == "AVAILABLE"
    assert result["absolute_change"] == -25.0
    assert result["percent_change"] == pytest.approx(-0.25)


def test_mtd_month_reset_is_not_a_weekly_comparison() -> None:
    records = (
        {"period_scope": "MTD_OPERATING", "business_as_of_date": "2026-07-31", "coverage_start_date": "2026-07-01", "coverage_end_date": "2026-07-31", "net_sales": 100.0},
        {"period_scope": "MTD_OPERATING", "business_as_of_date": "2026-08-02", "coverage_start_date": "2026-08-01", "coverage_end_date": "2026-08-02", "net_sales": 10.0},
    )
    assert compare_equal_weekly(records) == {"availability": "NOT_COMPARABLE", "reason": "MTD_RESET_OR_NON_WEEKLY_PERIOD"}


def test_assembly_preserves_cutoffs_lineage_ytd_and_no_new_tables(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database)
    with sqlite3.connect(database) as connection:
        before = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    snapshot = BusinessHealthAssembler(database).assemble(_walmart())
    with sqlite3.connect(database) as connection:
        after = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert before == after
    assert snapshot.control_week == "2026-W33"
    assert "week" not in snapshot.to_dict()
    assert snapshot.to_dict()["control_week"] == "2026-W33"
    assert snapshot.facts["actual_sales"].data_through_date == "2026-08-02"
    assert snapshot.facts["actual_cm"].data_through_date == "2026-08-10"
    assert snapshot.facts["actual_cm"].import_batch_id == "BATCH-1"
    assert snapshot.facts["inventory_condition"].source_artifact == "sku.parquet"
    assert snapshot.facts["ytd_actual_cm"].value is None
    assert snapshot.facts["ytd_actual_cm"].freshness == "SOURCE_NOT_AVAILABLE"
    assert snapshot.derived_control_metrics["sales_cm_common_cutoff_metric"].value is None
    assert snapshot.derived_control_metrics["sales_cm_common_cutoff_metric"].availability == "NOT_COMPARABLE"
    assert snapshot.interpretation["overall_status"] == "UNRESOLVED"


def test_explicit_control_week_is_not_a_measurement_week(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database)
    snapshot = BusinessHealthAssembler(database).assemble(_walmart(), control_week="2026-W34")
    assert snapshot.control_week == "2026-W34"
    assert snapshot.facts["actual_sales"].period_end == "2026-08-02"
    with pytest.raises(Exception, match="CONTROL_WEEK_INVALID"):
        BusinessHealthAssembler(database).assemble(_walmart(), control_week="2026W34")


def test_negative_official_net_sales_is_preserved(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database)
    snapshot = BusinessHealthAssembler(database).assemble(_walmart(net_sales=-694.21))
    assert snapshot.facts["actual_sales"].value == -694.21
    assert snapshot.derived_control_metrics["sales_attainment_pct"].value == pytest.approx(-694.21 / 200.0)


def test_nullable_bp_prevents_attainment(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database, bp_sales=None)
    snapshot = BusinessHealthAssembler(database).assemble(_walmart())
    metric = snapshot.derived_control_metrics["sales_attainment_pct"]
    assert snapshot.facts["bp_sales"].value is None
    assert metric.value is None
    assert metric.availability == "SOURCE_NOT_AVAILABLE"


def test_feishu_dry_run_uses_only_existing_fields_and_reports_unmapped(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database)
    snapshot = BusinessHealthAssembler(database).assemble(_walmart())
    schema_path = Path(__file__).parents[1] / "config" / "feishu_schema.yaml"
    dry_run = build_feishu_dry_run(snapshot, schema_path)
    schema = __import__("yaml").safe_load(schema_path.read_text(encoding="utf-8"))
    table = next(item for item in schema["tables"] if item["name"] == "01 Business Health")
    allowed = {item["name"] for item in table["fields"]}
    assert set(dry_run.record).issubset(allowed)
    assert dry_run.external_write_performed is False
    assert dry_run.record["Data As Of"] is None
    assert dry_run.record["Overall Health"] == "UNKNOWN"
    assert dry_run.record["Human Reviewed"] is False
    assert {item["metric"] for item in dry_run.diagnostics["unmapped_metrics"]} >= {"actual_cm", "roas"}


def test_preview_v2_uses_pending_rule_state_and_maps_control_week(tmp_path: Path) -> None:
    database = tmp_path / "metrics.sqlite3"
    _database(database)
    snapshot = BusinessHealthAssembler(database).assemble(
        _walmart(net_sales=-694.21), control_week="2026-W33"
    )
    schema_path = Path(__file__).parents[1] / "config" / "feishu_schema.yaml"
    dry_run = build_feishu_dry_run(snapshot, schema_path)
    preview = render_preview_v2(snapshot, dry_run)
    assert dry_run.record["Week"] == "2026-W33"
    assert "Net Sales Actual" in preview
    assert "Data Coverage:** `PARTIAL`" in preview
    assert "Data Confidence: `PENDING_RULE_APPROVAL`" in preview
    assert "PENDING_RULE_APPROVAL" in preview
    assert "YTD CM: `SOURCE_NOT_AVAILABLE`" in preview
    assert "No rule, schema change, Signal, Action, or external write was activated" in preview
