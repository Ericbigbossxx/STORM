from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from storm.structured_metrics.schema import (
    BpTargetMonthly,
    CmSnapshot,
    DataException,
    DimSku,
    ImportPlan,
    PeriodType,
    Platform,
    ReconciliationResult,
)
from storm.structured_metrics.store import StructuredMetricsStore, StoreValidationError


def sample_plan(*, file_hash: str = "A" * 64, source_period: str = "2026-08|MTD", snapshot_date: str = "2026-08-11") -> ImportPlan:
    dim = DimSku(
        Platform.THD, "SKU-1", "Sunseeker", "Robot", "Mower", "first_party", "sell_in"
    )
    bp = BpTargetMonthly(2026, 8, Platform.THD, "SKU-1", 10.0, 100.0, None, None, "KPI Rawdata", (2, 3))
    cm = CmSnapshot(
        snapshot_date, "2026-08-10", PeriodType.MTD, Platform.THD, "Sunseeker", "Robot",
        1.0, 20.0, 5.0, 0.25, None, None, 10.0, 100.0, None, None,
        "PRIMARY_SELL_IN_EXCLUDES_DFC", "sell_in", "Overview", "J259:J320",
    )
    reconciliation = ReconciliationResult("PLATFORM", "THD", "actual_sales", 20.0, 20.0, 0.0, 0.01, "PASS")
    return ImportPlan(
        "source.xlsx", file_hash, "OFFICIAL_CM_WORKBOOK", source_period, snapshot_date, "2026-08-10",
        3, (dim,), (bp,), (cm,),
        (DataException("UNMAPPED_SKU", "preserved test exception", raw_key="UNKNOWN"),),
        (reconciliation,), {"THD": {"actual_sales": 20.0}},
    )


def test_schema_contains_phase_1_contract_tables(tmp_path):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")
    store.initialize()
    with store.connect() as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"DIM_SKU", "IMPORT_BATCH", "DATA_EXCEPTION", "FACT_BP_TARGET_MONTHLY", "FACT_CM_SNAPSHOT"} <= names


def test_import_is_idempotent_and_records_duplicate(tmp_path):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")
    first = store.import_plan(sample_plan())
    second = store.import_plan(sample_plan())
    assert first["status"] == "COMMITTED"
    assert second == {"status": "DUPLICATE", "import_batch_id": first["import_batch_id"], "loaded_row_count": 0}
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM IMPORT_BATCH").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM FACT_CM_SNAPSHOT").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM DATA_EXCEPTION WHERE exception_type='DUPLICATE_IMPORT'").fetchone()[0] == 1


def test_historical_snapshots_are_preserved(tmp_path):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")
    store.import_plan(sample_plan())
    second = sample_plan(file_hash="B" * 64, source_period="2026-09|MTD", snapshot_date="2026-09-11")
    second = replace(
        second,
        cm_snapshots=(replace(second.cm_snapshots[0], snapshot_date="2026-09-11", data_through_date="2026-09-10"),),
        data_through_date="2026-09-10",
    )
    store.import_plan(second)
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM IMPORT_BATCH").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM FACT_CM_SNAPSHOT").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM DIM_SKU").fetchone()[0] == 1


def test_null_metrics_remain_null_and_exceptions_are_not_dropped(tmp_path):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")
    store.import_plan(sample_plan())
    with store.connect() as connection:
        bp = connection.execute("SELECT bp_cm, bp_cm_pct FROM FACT_BP_TARGET_MONTHLY").fetchone()
        cm = connection.execute("SELECT actual_cm, actual_cm_pct FROM FACT_CM_SNAPSHOT").fetchone()
        exception = connection.execute("SELECT raw_key FROM DATA_EXCEPTION WHERE exception_type='UNMAPPED_SKU'").fetchone()
    assert tuple(bp) == (None, None)
    assert tuple(cm) == (None, None)
    assert exception[0] == "UNKNOWN"


def test_invalid_platform_is_rejected_before_write(tmp_path):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")
    plan = sample_plan()
    invalid_dim = replace(plan.dim_skus[0], platform="AMAZON")  # type: ignore[arg-type]
    invalid = replace(plan, dim_skus=(invalid_dim,))
    with pytest.raises(StoreValidationError, match="invalid platform"):
        store.import_plan(invalid)
    assert not store.database_path.exists()


def test_transaction_rolls_back_after_mid_import_failure(tmp_path, monkeypatch):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")

    def fail_after_batch(connection: sqlite3.Connection, batch_id: str, plan: ImportPlan) -> None:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(store, "_insert_bp_facts", fail_after_batch)
    with pytest.raises(RuntimeError, match="injected failure"):
        store.import_plan(sample_plan())
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM IMPORT_BATCH").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM DIM_SKU").fetchone()[0] == 0


def test_failed_reconciliation_blocks_database_creation(tmp_path):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")
    failure = ReconciliationResult("PLATFORM", "THD", "actual_sales", 20.0, 21.0, 1.0, 0.01, "FAIL")
    plan = replace(sample_plan(), reconciliations=(failure,))
    with pytest.raises(StoreValidationError, match="reconciliation failed"):
        store.import_plan(plan)
    assert not store.database_path.exists()


def test_nonblocking_derived_view_failure_commits_with_warning_status(tmp_path):
    store = StructuredMetricsStore(tmp_path / "metrics.sqlite3")
    warning = ReconciliationResult(
        "BP_DERIVED_VIEW_PLATFORM", "WALMART_MP", "bp_sales",
        0.0, 100.0, 100.0, 0.01, "FAIL", False, "BROKEN_DERIVED_FORMULA",
    )
    plan = replace(sample_plan(), reconciliations=(warning,))
    result = store.import_plan(plan)
    assert result["status"] == "COMMITTED"
    with store.connect() as connection:
        status = connection.execute("SELECT reconciliation_status FROM IMPORT_BATCH").fetchone()[0]
    assert status == "PASS_WITH_WARNINGS"
