"""Transactional SQLite store for immutable Phase 1 import batches."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .schema import DDL, ImportPlan, Platform


class StoreValidationError(ValueError):
    """Raised before a plan can alter persisted state."""


class ReconciliationError(StoreValidationError):
    """Raised when an import does not reconcile within configured tolerance."""


class StructuredMetricsStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(DDL)

    @staticmethod
    def validate_plan(plan: ImportPlan) -> None:
        allowed = {item.value for item in Platform}
        for item in (*plan.dim_skus, *plan.bp_targets, *plan.cm_snapshots):
            platform = item.platform.value if isinstance(item.platform, Platform) else str(item.platform)
            if platform not in allowed:
                raise StoreValidationError(f"invalid platform: {platform}")
        if any(row.result != "PASS" and row.is_blocking for row in plan.reconciliations):
            failures = [
                f"{row.level}:{row.key}:{row.metric}"
                for row in plan.reconciliations
                if row.result != "PASS" and row.is_blocking
            ]
            raise ReconciliationError("reconciliation failed: " + ", ".join(failures[:10]))
        dim_keys = {(row.platform.value, row.canonical_sku) for row in plan.dim_skus}
        for row in plan.bp_targets:
            if (row.platform.value, row.canonical_sku) not in dim_keys:
                raise StoreValidationError(f"BP row has no DIM_SKU mapping: {row.platform.value}/{row.canonical_sku}")
        if not plan.file_hash or len(plan.file_hash) != 64:
            raise StoreValidationError("file_hash must be a SHA-256 hex digest")

    def find_duplicate(self, plan: ImportPlan) -> sqlite3.Row | None:
        if not self.database_path.exists():
            return None
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM IMPORT_BATCH WHERE file_hash=? AND report_type=? AND source_period=?",
                (plan.file_hash, plan.report_type, plan.source_period),
            ).fetchone()

    def import_plan(self, plan: ImportPlan) -> dict[str, str | int]:
        self.validate_plan(plan)
        self.initialize()
        duplicate = self.find_duplicate(plan)
        if duplicate is not None:
            self._record_duplicate(str(duplicate["import_batch_id"]), plan)
            return {"status": "DUPLICATE", "import_batch_id": str(duplicate["import_batch_id"]), "loaded_row_count": 0}

        batch_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        reconciliation_json = json.dumps([asdict(row) for row in plan.reconciliations], ensure_ascii=False, sort_keys=True)
        reconciliation_status = (
            "PASS_WITH_WARNINGS"
            if any(row.result != "PASS" and not row.is_blocking for row in plan.reconciliations)
            else "PASS"
        )
        loaded = len(plan.dim_skus) + len(plan.bp_targets) + len(plan.cm_snapshots)
        rejected = sum(1 for item in plan.exceptions if item.severity.value == "ERROR")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO IMPORT_BATCH VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_id, plan.source_filename, plan.file_hash, plan.report_type, plan.source_period,
                    plan.snapshot_date, plan.data_through_date, now, plan.input_row_count, loaded, rejected,
                    json.dumps(plan.source_totals, ensure_ascii=False, sort_keys=True), reconciliation_json,
                    reconciliation_status, "COMMITTED",
                ),
            )
            self._insert_dim_skus(connection, batch_id, plan)
            self._insert_bp_facts(connection, batch_id, plan)
            self._insert_cm_facts(connection, batch_id, plan)
            self._insert_exceptions(connection, batch_id, plan, now)
        return {"status": "COMMITTED", "import_batch_id": batch_id, "loaded_row_count": loaded}

    def _record_duplicate(self, batch_id: str, plan: ImportPlan) -> None:
        now = datetime.now(timezone.utc).isoformat()
        description = f"duplicate identity {plan.file_hash}/{plan.report_type}/{plan.source_period}"
        with self.connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO DATA_EXCEPTION
                (exception_id, import_batch_id, exception_type, severity, description, created_at)
                VALUES (?, ?, 'DUPLICATE_IMPORT', 'WARNING', ?, ?)""",
                (str(uuid.uuid4()), batch_id, description, now),
            )

    @staticmethod
    def _insert_dim_skus(connection: sqlite3.Connection, batch_id: str, plan: ImportPlan) -> None:
        for row in plan.dim_skus:
            existing = connection.execute(
                "SELECT * FROM DIM_SKU WHERE platform=? AND canonical_sku=?",
                (row.platform.value, row.canonical_sku),
            ).fetchone()
            comparable = (
                row.platform_sku, row.brand, row.power_source, row.category,
                row.business_model, row.primary_sales_basis,
            )
            if existing is not None:
                stored = tuple(existing[name] for name in (
                    "platform_sku", "brand", "power_source", "category", "business_model", "primary_sales_basis"
                ))
                if stored != comparable:
                    raise StoreValidationError(
                        f"DIM_SKU contract changed without review: {row.platform.value}/{row.canonical_sku}"
                    )
                continue
            connection.execute(
                """INSERT INTO DIM_SKU
                (platform, canonical_sku, platform_sku, brand, power_source, category, business_model,
                 primary_sales_basis, first_import_batch_id, source_sheet, source_row)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row.platform.value, row.canonical_sku, row.platform_sku, row.brand, row.power_source,
                 row.category, row.business_model, row.primary_sales_basis, batch_id, row.source_sheet, row.source_row),
            )

    @staticmethod
    def _insert_bp_facts(connection: sqlite3.Connection, batch_id: str, plan: ImportPlan) -> None:
        connection.executemany(
            """INSERT INTO FACT_BP_TARGET_MONTHLY
            (year, month, platform, canonical_sku, bp_units, bp_sales, bp_cm, bp_cm_pct,
             import_batch_id, source_sheet, source_rows_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (row.year, row.month, row.platform.value, row.canonical_sku, row.bp_units, row.bp_sales,
                 row.bp_cm, row.bp_cm_pct, batch_id, row.source_sheet, json.dumps(row.source_rows))
                for row in plan.bp_targets
            ],
        )

    @staticmethod
    def _insert_cm_facts(connection: sqlite3.Connection, batch_id: str, plan: ImportPlan) -> None:
        connection.executemany(
            """INSERT INTO FACT_CM_SNAPSHOT
            (snapshot_date, data_through_date, period_type, platform, brand, power_source,
             actual_units, actual_sales, actual_gm, actual_gm_pct, actual_cm, actual_cm_pct,
             bp_units, bp_sales, bp_cm, bp_cm_pct, cm_basis, primary_sales_basis,
             import_batch_id, source_sheet, source_range)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (row.snapshot_date, row.data_through_date, row.period_type.value, row.platform.value,
                 row.brand, row.power_source, row.actual_units, row.actual_sales, row.actual_gm,
                 row.actual_gm_pct, row.actual_cm, row.actual_cm_pct, row.bp_units, row.bp_sales,
                 row.bp_cm, row.bp_cm_pct, row.cm_basis, row.primary_sales_basis, batch_id,
                 row.source_sheet, row.source_range)
                for row in plan.cm_snapshots
            ],
        )

    @staticmethod
    def _insert_exceptions(connection: sqlite3.Connection, batch_id: str, plan: ImportPlan, now: str) -> None:
        connection.executemany(
            """INSERT INTO DATA_EXCEPTION
            (exception_id, import_batch_id, exception_type, severity, platform, raw_key,
             source_sheet, source_row, source_range, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (str(uuid.uuid4()), batch_id, row.exception_type, row.severity.value, row.platform,
                 row.raw_key, row.source_sheet, row.source_row, row.source_range, row.description, now)
                for row in plan.exceptions
            ],
        )
