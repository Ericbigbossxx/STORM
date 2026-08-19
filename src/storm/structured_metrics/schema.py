"""Phase 1 structured-metrics schema and immutable import payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


SCHEMA_VERSION = 1


class Platform(StrEnum):
    WALMART_MP = "WALMART_MP"
    THD = "THD"
    LOWES = "LOWES"


class PeriodType(StrEnum):
    MTD = "MTD"
    YTD = "YTD"


class ExceptionSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DataException:
    exception_type: str
    description: str
    severity: ExceptionSeverity = ExceptionSeverity.ERROR
    platform: str | None = None
    raw_key: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_range: str | None = None


@dataclass(frozen=True)
class DimSku:
    platform: Platform
    canonical_sku: str
    brand: str
    power_source: str
    category: str | None
    business_model: str
    primary_sales_basis: str
    platform_sku: str | None = None
    source_sheet: str = "SKU Mapping"
    source_row: int | None = None


@dataclass(frozen=True)
class BpTargetMonthly:
    year: int
    month: int
    platform: Platform
    canonical_sku: str
    bp_units: float | None
    bp_sales: float | None
    bp_cm: float | None
    bp_cm_pct: float | None
    source_sheet: str
    source_rows: tuple[int, ...]


@dataclass(frozen=True)
class CmSnapshot:
    snapshot_date: str
    data_through_date: str
    period_type: PeriodType
    platform: Platform
    brand: str
    power_source: str
    actual_units: float | None
    actual_sales: float | None
    actual_gm: float | None
    actual_gm_pct: float | None
    actual_cm: float | None
    actual_cm_pct: float | None
    bp_units: float | None
    bp_sales: float | None
    bp_cm: float | None
    bp_cm_pct: float | None
    cm_basis: str
    primary_sales_basis: str
    source_sheet: str
    source_range: str


@dataclass(frozen=True)
class ReconciliationResult:
    level: str
    key: str
    metric: str
    official_value: float | None
    imported_value: float | None
    variance: float | None
    tolerance: float
    result: str
    is_blocking: bool = True
    classification: str | None = None


@dataclass(frozen=True)
class ImportPlan:
    source_filename: str
    file_hash: str
    report_type: str
    source_period: str
    snapshot_date: str
    data_through_date: str
    input_row_count: int
    dim_skus: tuple[DimSku, ...]
    bp_targets: tuple[BpTargetMonthly, ...]
    cm_snapshots: tuple[CmSnapshot, ...]
    exceptions: tuple[DataException, ...] = ()
    reconciliations: tuple[ReconciliationResult, ...] = ()
    source_totals: dict[str, Any] = field(default_factory=dict)


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS IMPORT_BATCH (
    import_batch_id TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    report_type TEXT NOT NULL,
    source_period TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    data_through_date TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    input_row_count INTEGER NOT NULL,
    loaded_row_count INTEGER NOT NULL,
    rejected_row_count INTEGER NOT NULL,
    source_totals_json TEXT NOT NULL,
    reconciliation_json TEXT NOT NULL,
    reconciliation_status TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(file_hash, report_type, source_period)
);

CREATE TABLE IF NOT EXISTS DATA_EXCEPTION (
    exception_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES IMPORT_BATCH(import_batch_id),
    exception_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('WARNING', 'ERROR')),
    platform TEXT,
    raw_key TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    source_range TEXT,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(import_batch_id, exception_type, description, source_sheet, source_row)
);

CREATE TABLE IF NOT EXISTS DIM_SKU (
    platform TEXT NOT NULL CHECK (platform IN ('WALMART_MP', 'THD', 'LOWES')),
    canonical_sku TEXT NOT NULL,
    platform_sku TEXT,
    brand TEXT NOT NULL,
    power_source TEXT NOT NULL,
    category TEXT,
    business_model TEXT NOT NULL,
    primary_sales_basis TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    first_import_batch_id TEXT NOT NULL REFERENCES IMPORT_BATCH(import_batch_id),
    source_sheet TEXT NOT NULL,
    source_row INTEGER,
    PRIMARY KEY(platform, canonical_sku)
);

CREATE TABLE IF NOT EXISTS FACT_BP_TARGET_MONTHLY (
    bp_target_id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    platform TEXT NOT NULL CHECK (platform IN ('WALMART_MP', 'THD', 'LOWES')),
    canonical_sku TEXT NOT NULL,
    bp_units REAL,
    bp_sales REAL,
    bp_cm REAL,
    bp_cm_pct REAL,
    import_batch_id TEXT NOT NULL REFERENCES IMPORT_BATCH(import_batch_id),
    source_sheet TEXT NOT NULL,
    source_rows_json TEXT NOT NULL,
    FOREIGN KEY(platform, canonical_sku) REFERENCES DIM_SKU(platform, canonical_sku),
    UNIQUE(import_batch_id, year, month, platform, canonical_sku)
);

CREATE TABLE IF NOT EXISTS FACT_CM_SNAPSHOT (
    cm_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    data_through_date TEXT NOT NULL,
    period_type TEXT NOT NULL CHECK (period_type IN ('MTD', 'YTD')),
    platform TEXT NOT NULL CHECK (platform IN ('WALMART_MP', 'THD', 'LOWES')),
    brand TEXT NOT NULL,
    power_source TEXT NOT NULL,
    actual_units REAL,
    actual_sales REAL,
    actual_gm REAL,
    actual_gm_pct REAL,
    actual_cm REAL,
    actual_cm_pct REAL,
    bp_units REAL,
    bp_sales REAL,
    bp_cm REAL,
    bp_cm_pct REAL,
    cm_basis TEXT NOT NULL,
    primary_sales_basis TEXT NOT NULL,
    import_batch_id TEXT NOT NULL REFERENCES IMPORT_BATCH(import_batch_id),
    source_sheet TEXT NOT NULL,
    source_range TEXT NOT NULL,
    UNIQUE(snapshot_date, period_type, platform, brand, power_source, cm_basis)
);
"""
