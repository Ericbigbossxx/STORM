"""Read the existing authoritative YTD fields without summing snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .normalization import as_number, normalize_text
from .sku_bp import extract_sku_bp


def _usable(value: Any) -> float | None:
    if isinstance(value, str) and value.startswith("#"):
        return None
    return as_number(value)


def _overall_actual_sales(workbook: Any, through_month: int) -> tuple[float | None, dict[str, Any]]:
    sheet = workbook["KPI Trend"]
    months = [sheet.cell(2, column).value for column in range(3, 15)]
    month_columns = [column for column, label in enumerate(months, 3) if column - 2 <= through_month and label]
    row = next((row for row in range(3, 30) if normalize_text(sheet.cell(row, 2).value) == "GMV"), None)
    if row is None:
        return None, {"status": "N/A", "reason": "KPI Trend overall GMV row missing"}
    values = [_usable(sheet.cell(row, column).value) for column in month_columns]
    if any(value is None for value in values):
        return None, {"status": "N/A", "reason": "KPI Trend GMV has an unverified month"}
    return sum(values), {"status": "AVAILABLE", "sheet": "KPI Trend", "row": row, "month_columns": month_columns}


def _overall_actual_cm(workbook: Any, through_month: int) -> tuple[float | None, dict[str, Any]]:
    sheet = workbook["KPI Trend"]
    row = next((row for row in range(3, 30) if normalize_text(sheet.cell(row, 2).value) == "CM"), None)
    if row is None:
        return None, {"status": "N/A", "reason": "KPI Trend overall CM row missing"}
    values = [_usable(sheet.cell(row, column).value) for column in range(3, through_month + 3)]
    if any(value is None for value in values):
        return None, {"status": "N/A", "reason": "KPI Trend CM contains source error/unavailable month"}
    return sum(values), {"status": "AVAILABLE", "sheet": "KPI Trend", "row": row}


def extract_ytd_metrics(workbook_path: Path, *, year: int, through_month: int) -> dict[str, Any]:
    """Extract directly reported YTD Sales/BP and retain unavailable CM as N/A."""
    workbook = load_workbook(workbook_path, read_only=True, data_only=True, keep_links=False)
    try:
        actual_sales, actual_sales_source = _overall_actual_sales(workbook, through_month)
        actual_cm, actual_cm_source = _overall_actual_cm(workbook, through_month)
    finally:
        workbook.close()
    bp_rows = []
    bp_sources = []
    for month in range(1, through_month + 1):
        extraction = extract_sku_bp(workbook_path, year=year, month=month)
        bp_rows.extend(extraction["rows"])
        bp_sources.append({"month": month, "source_row_count": extraction["source_row_count"]})
    bp_sales = sum(float(row["bp_sales"]) for row in bp_rows)
    gap = actual_sales - bp_sales if actual_sales is not None else None
    return {
        "period": "YTD",
        "year": year,
        "through_month": through_month,
        "source": "AUTHORITATIVE_CM_BP_WORKBOOK",
        "actual_sales": actual_sales,
        "bp_sales": bp_sales,
        "sales_gap": gap,
        "attainment": actual_sales / bp_sales if actual_sales is not None and bp_sales > 0 else None,
        "actual_cm": actual_cm,
        "bp_cm": None,
        "cm_gap": None,
        "actual_cm_pct": None,
        "bp_cm_pct": None,
        "availability": {
            "actual_sales": actual_sales_source,
            "bp_sales": {"status": "AVAILABLE", "sheet": "KPI Rawdata", "months": bp_sources},
            "actual_cm": actual_cm_source,
            "bp_cm": {"status": "N/A", "reason": "No comparable direct YTD BP CM source row verified"},
        },
    }
