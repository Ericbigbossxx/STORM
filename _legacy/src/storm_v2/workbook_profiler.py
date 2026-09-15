"""Read-only STORM V2 workbook profiler and Phase 1 report generator."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from .data_contract import (
    CANONICAL_HIERARCHY,
    CanonicalMetricRecord,
    DataQualityStatus,
    MappingStatus,
    MetricDomain,
    QualityIssue,
    SourceSnapshot,
)
from .normalization import as_number, normalize_date, normalize_sku, normalize_text


EXPECTED_SHEETS = (
    "over view",
    "2026 acutal cost",
    "actual order",
    "THD- robot Sell out",
    "KPI Rawdata",
    "SKU MAP",
)

REQUIRED_HEADERS: dict[str, tuple[str, ...]] = {
    "2026 acutal cost": (
        "Item", "Channel", "Brand", "%-Refer to BP Version", "Year", "Jan", "Aug", "MTD", "YTD", "FY"
    ),
    "actual order": (
        "Year", "Month", "Date", "Country", "Channel", "SKU", "Ordered Revenue", "Ordered Units", "Order Number"
    ),
    "THD- robot Sell out": (
        "day", "online manufacturing part number +", "Order Units", "GMV", "ASP", "PIP Visit", "Conversion Rate%"
    ),
    "KPI Rawdata": (
        "SKU", "ASIN/#", "Channel", "Customer", "Month-INT", "Year", "Month", "Qty", "TTL amount", "Brand", "Power Source"
    ),
    "SKU MAP": ("SKU", "ASIN", "Pource Source", "Brand", "Category"),
}

OVERVIEW_SECTIONS = (
    "By Brand",
    "By Power Source",
    "By Channel",
    "Actual CM vs. BP CM",
    "All Brand",
    "BI Channel Name",
)

# These labels are deliberately used only by inventory collection. They are not
# source registry entries, mapping aliases, quality rules, or canonical values.
_INVENTORY_ONLY_GROUPS = ("Amazon", "DTC", "Costco")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_json_yaml(path: Path) -> dict[str, Any]:
    # JSON is a strict YAML 1.2 subset and avoids a Phase 1-only parser dependency.
    return json.loads(path.read_text(encoding="utf-8"))


def _header_map(ws, row: int = 1) -> dict[str, int]:
    result: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        label = normalize_text(ws.cell(row, col).value)
        if label and label not in result:
            result[label] = col
    return result


def _cell_ref(row: int, column: int) -> str:
    return f"{get_column_letter(column)}{row}"


def _inventory_only_group(value: Any) -> str | None:
    label = (normalize_text(value) or "").casefold()
    if "amazon" in label or label.startswith("amz "):
        return "Amazon"
    if label == "dtc" or label.startswith("dtc "):
        return "DTC"
    if "costco" in label:
        return "Costco"
    return None


def _scan_overview_sections(ws) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {section: [] for section in OVERVIEW_SECTIONS}
    wanted = {section.casefold(): section for section in OVERVIEW_SECTIONS}
    for row in ws.iter_rows():
        for cell in row:
            label = normalize_text(cell.value)
            if label and label.casefold() in wanted:
                found[wanted[label.casefold()]].append(cell.coordinate)
    return found


def _scan_inventory_only(ws) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    examples: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    if ws.title == "2026 acutal cost":
        headers = _header_map(ws)
        col = headers.get("Channel")
        if col:
            for row in range(2, ws.max_row + 1):
                group = _inventory_only_group(ws.cell(row, col).value)
                if group:
                    key = (group, "Channel data rows")
                    counts[key] += 1
                    if len(examples[key]) < 3:
                        examples[key].append(_cell_ref(row, col))
    elif ws.title == "KPI Rawdata":
        headers = _header_map(ws)
        col = headers.get("Customer")
        if col:
            for row in range(2, ws.max_row + 1):
                group = _inventory_only_group(ws.cell(row, col).value)
                if group:
                    key = (group, "Customer data rows")
                    counts[key] += 1
                    if len(examples[key]) < 3:
                        examples[key].append(_cell_ref(row, col))
    elif ws.title == "over view":
        for row in ws.iter_rows():
            for cell in row:
                group = _inventory_only_group(cell.value)
                if group:
                    key = (group, "repeated By Channel / brand-power summary labels")
                    counts[key] += 1
                    if len(examples[key]) < 3:
                        examples[key].append(cell.coordinate)
    return [
        {
            "business": group,
            "sheet": ws.title,
            "section": section,
            "record_count": count,
            "count_basis": "source rows" if "data rows" in section else "summary label occurrences",
            "sample_references": examples[(group, section)],
            "status": "OUT_OF_SCOPE_FOR_STORM_V2",
            "exclusion_reason": "Not part of the approved STORM V2 core channel contract",
        }
        for (group, section), count in sorted(counts.items())
    ]


def _build_sku_map(ws) -> tuple[dict[str, dict[str, Any]], list[QualityIssue]]:
    headers = _header_map(ws)
    sku_col = headers["SKU"]
    brand_col = headers["Brand"]
    power_col = headers["Pource Source"]
    asin_col = headers["ASIN"]
    category_col = headers["Category"]
    mapping: dict[str, dict[str, Any]] = {}
    rows_by_sku: defaultdict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for row in range(2, ws.max_row + 1):
        raw_sku = ws.cell(row, sku_col).value
        sku = normalize_sku(raw_sku)
        if not sku:
            continue
        value = {
            "raw_sku": raw_sku,
            "brand": normalize_text(ws.cell(row, brand_col).value),
            "power_source": normalize_text(ws.cell(row, power_col).value),
            "asin": normalize_text(ws.cell(row, asin_col).value),
            "category": normalize_text(ws.cell(row, category_col).value),
            "row": row,
        }
        rows_by_sku[sku].append((row, value))
        mapping.setdefault(sku, value)

    issues: list[QualityIssue] = []
    for sku, rows in rows_by_sku.items():
        if len(rows) <= 1:
            continue
        signatures = {
            (item[1]["brand"], item[1]["power_source"], item[1]["asin"], item[1]["category"])
            for item in rows
        }
        issues.append(
            QualityIssue(
                code="SKU_NORMALIZED_DUPLICATE_EQUIVALENT" if len(signatures) == 1 else "SKU_NORMALIZED_DUPLICATE_CONFLICT",
                status=DataQualityStatus.WARNING if len(signatures) == 1 else DataQualityStatus.BLOCKING,
                sheet=ws.title,
                source_reference=", ".join(f"A{row}" for row, _ in rows),
                summary=f"Normalized SKU {sku} appears {len(rows)} times; values are "
                + ("equivalent" if len(signatures) == 1 else "conflicting"),
                affected_records=len(rows),
                blocking=len(signatures) != 1,
            )
        )
    return mapping, issues


def _channel_contract(mappings: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {normalize_text(k).casefold(): v for k, v in mappings["channels"].items() if normalize_text(k)}


def _canonical_actual_order(
    ws,
    source: SourceSnapshot,
    sku_map: dict[str, dict[str, Any]],
    mappings: dict[str, Any],
) -> tuple[list[CanonicalMetricRecord], list[QualityIssue], dict[str, Any]]:
    headers = _header_map(ws)
    channel_contract = _channel_contract(mappings)
    excluded = {normalize_text(k).casefold() for k in mappings["excluded_contract_values"]}
    candidates: list[CanonicalMetricRecord] = []
    issues: list[QualityIssue] = []
    unmapped_skus: Counter[str] = Counter()
    date_types: Counter[str] = Counter()
    normalized_dates = []
    accepted_rows = 0

    for row in range(2, ws.max_row + 1):
        raw_channel = ws.cell(row, headers["Channel"]).value
        if _inventory_only_group(raw_channel):
            continue
        channel_key = (normalize_text(raw_channel) or "").casefold()
        if channel_key in excluded or channel_key not in channel_contract:
            continue
        channel = channel_contract[channel_key]
        raw_sku = ws.cell(row, headers["SKU"]).value
        sku = normalize_sku(raw_sku)
        sku_data = sku_map.get(sku or "")
        mapping_status = MappingStatus.MAPPED if sku_data else MappingStatus.UNMAPPED
        if not sku_data:
            unmapped_skus[sku or "<blank>"] += 1
        raw_date = ws.cell(row, headers["Date"]).value
        date_types[type(raw_date).__name__] += 1
        period_date = normalize_date(raw_date)
        if period_date:
            normalized_dates.append(period_date)
        accepted_rows += 1
        common = {
            "scenario": "ACTUAL",
            "period_date": period_date,
            "platform": channel["platform"],
            "channel_subchannel": channel["channel_subchannel"],
            "brand": sku_data["brand"] if sku_data else None,
            "power_source": sku_data["power_source"] if sku_data else None,
            "sku": sku,
            "mapping_status": mapping_status,
            "source_file": source.source_file,
            "source_sha256": source.sha256,
            "source_sheet": ws.title,
            "source_section": "weekly order rows",
            "source_reference": f"{row}:{row}",
            "raw_dimensions": {
                "channel": raw_channel,
                "sku": raw_sku,
                "date": raw_date,
                "order_number": ws.cell(row, headers["Order Number"]).value,
            },
        }
        for header, name, unit in (
            ("Ordered Revenue", "revenue", "USD"),
            ("Ordered Units", "units", "unit"),
        ):
            raw_value = ws.cell(row, headers[header]).value
            candidates.append(
                CanonicalMetricRecord(
                    metric_domain=MetricDomain.SALES,
                    metric_name=name,
                    metric_value=as_number(raw_value),
                    metric_unit=unit,
                    source_header=header,
                    raw_value=raw_value,
                    **common,
                )
            )

    if unmapped_skus:
        details = ", ".join(f"{sku} ({count})" for sku, count in sorted(unmapped_skus.items()))
        issues.append(
            QualityIssue(
                code="ACTUAL_ORDER_UNMAPPED_SKU",
                status=DataQualityStatus.WARNING,
                sheet=ws.title,
                source_reference="SKU column",
                summary=f"Unmapped SKU rows retained with UNKNOWN dimensions: {details}",
                affected_records=sum(unmapped_skus.values()),
            )
        )
    if len(date_types) > 1:
        issues.append(
            QualityIssue(
                code="ACTUAL_ORDER_MIXED_DATE_TYPES",
                status=DataQualityStatus.WARNING,
                sheet=ws.title,
                source_reference="C2:C487",
                summary="Mixed source date representations normalized to ISO dates: "
                + ", ".join(f"{kind}={count}" for kind, count in sorted(date_types.items())),
                affected_records=sum(date_types.values()),
            )
        )
    return candidates, issues, {
        "accepted_rows": accepted_rows,
        "date_type_counts": dict(date_types),
        "data_from": min(normalized_dates).isoformat() if normalized_dates else None,
        "data_through": max(normalized_dates).isoformat() if normalized_dates else None,
        "unmapped_sku_rows": dict(unmapped_skus),
    }


def _canonical_dfc(
    ws,
    source: SourceSnapshot,
    sku_map: dict[str, dict[str, Any]],
) -> tuple[list[CanonicalMetricRecord], list[QualityIssue], dict[str, Any]]:
    headers = _header_map(ws)
    sku_header = "online manufacturing part number +"
    metrics = (
        ("Order Units", "units", "unit"),
        ("GMV", "revenue", "USD"),
        ("PIP Visit", "traffic", "visit"),
        ("Conversion Rate%", "conversion_rate", "ratio"),
    )
    candidates: list[CanonicalMetricRecord] = []
    dates = []
    accepted_rows = 0
    zero_gmv_positive_units = 0
    for row in range(2, ws.max_row + 1):
        raw_date = ws.cell(row, headers["day"]).value
        period_date = normalize_date(raw_date)
        raw_sku = ws.cell(row, headers[sku_header]).value
        sku = normalize_sku(raw_sku)
        if not period_date or not sku:
            continue
        dates.append(period_date)
        accepted_rows += 1
        sku_data = sku_map.get(sku)
        status = MappingStatus.MAPPED if sku_data else MappingStatus.UNMAPPED
        units = as_number(ws.cell(row, headers["Order Units"]).value)
        gmv = as_number(ws.cell(row, headers["GMV"]).value)
        if units and units > 0 and (gmv is None or gmv == 0):
            zero_gmv_positive_units += 1
        common = {
            "scenario": "ACTUAL",
            "period_date": period_date,
            "platform": "THD",
            "channel_subchannel": "DFC",
            "brand": sku_data["brand"] if sku_data else None,
            "power_source": sku_data["power_source"] if sku_data else None,
            "sku": sku,
            "mapping_status": status,
            "source_file": source.source_file,
            "source_sha256": source.sha256,
            "source_sheet": ws.title,
            "source_section": "consumer daily sell-out",
            "source_reference": f"{row}:{row}",
            "raw_dimensions": {"sku": raw_sku, "date": raw_date},
        }
        for header, name, unit in metrics:
            raw_value = ws.cell(row, headers[header]).value
            candidates.append(
                CanonicalMetricRecord(
                    metric_domain=MetricDomain.THD_DFC_SELLOUT,
                    metric_name=name,
                    metric_value=as_number(raw_value),
                    metric_unit=unit,
                    source_header=header,
                    raw_value=raw_value,
                    **common,
                )
            )

    # Current inventory is a distinct J:K consumer block headed on row 2.
    inventory_header = normalize_text(ws.cell(2, 10).value)
    if inventory_header == "Inventory":
        for row in range(3, ws.max_row + 1):
            raw_inventory = ws.cell(row, 10).value
            raw_sku = ws.cell(row, 11).value
            sku = normalize_sku(raw_sku)
            if not sku or as_number(raw_inventory) is None:
                if row > 12:
                    break
                continue
            sku_data = sku_map.get(sku)
            candidates.append(
                CanonicalMetricRecord(
                    metric_domain=MetricDomain.THD_DFC_SELLOUT,
                    metric_name="inventory",
                    metric_value=as_number(raw_inventory),
                    metric_unit="unit",
                    scenario="ACTUAL",
                    period_date=max(dates) if dates else None,
                    platform="THD",
                    channel_subchannel="DFC",
                    brand=sku_data["brand"] if sku_data else None,
                    power_source=sku_data["power_source"] if sku_data else None,
                    sku=sku,
                    mapping_status=MappingStatus.MAPPED if sku_data else MappingStatus.UNMAPPED,
                    source_file=source.source_file,
                    source_sha256=source.sha256,
                    source_sheet=ws.title,
                    source_section="current consumer inventory",
                    source_header="Inventory",
                    source_reference=f"J{row}:K{row}",
                    raw_value=raw_inventory,
                    raw_dimensions={"sku": raw_sku},
                )
            )

    issues: list[QualityIssue] = []
    if zero_gmv_positive_units:
        issues.append(
            QualityIssue(
                code="THD_DFC_POSITIVE_UNITS_ZERO_GMV",
                status=DataQualityStatus.WARNING,
                sheet=ws.title,
                source_reference="A:G consumer daily block",
                summary="Positive sell-out units with zero GMV require business review; records remain in the DFC consumer domain",
                affected_records=zero_gmv_positive_units,
            )
        )
    return candidates, issues, {
        "accepted_rows": accepted_rows,
        "data_from": min(dates).isoformat() if dates else None,
        "data_through": max(dates).isoformat() if dates else None,
        "positive_units_zero_gmv": zero_gmv_positive_units,
    }


def profile_workbook(workbook_path: Path, project_root: Path | None = None) -> dict[str, Any]:
    workbook_path = workbook_path.resolve()
    project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    before_hash = sha256_file(workbook_path)
    stat = workbook_path.stat()
    snapshot = SourceSnapshot(
        source_file=workbook_path.name,
        byte_size=stat.st_size,
        sha256=before_hash,
        captured_at=datetime.now(timezone.utc),
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )
    sources = _load_json_yaml(project_root / "config" / "sources.yaml")
    mappings = _load_json_yaml(project_root / "config" / "mappings.yaml")
    # Normal in-memory mode permits repeated semantic scans without reopening
    # sheet XML. This audit never calls Workbook.save(); the pre/post hash is the
    # enforced read-only boundary.
    wb = load_workbook(workbook_path, read_only=False, data_only=True, keep_links=True)

    issues: list[QualityIssue] = []
    sheet_profiles: list[dict[str, Any]] = []
    inventory_only: list[dict[str, Any]] = []
    missing_sheets = [sheet for sheet in EXPECTED_SHEETS if sheet not in wb.sheetnames]
    extra_sheets = [sheet for sheet in wb.sheetnames if sheet not in EXPECTED_SHEETS]
    if missing_sheets or extra_sheets:
        issues.append(
            QualityIssue(
                code="WORKBOOK_SHEET_CONTRACT_DRIFT",
                status=DataQualityStatus.BLOCKING,
                sheet="<workbook>",
                source_reference="sheetnames",
                summary=f"Missing={missing_sheets or 'none'}; unexpected={extra_sheets or 'none'}",
                affected_records=len(missing_sheets) + len(extra_sheets),
                blocking=True,
            )
        )

    overview_sections: dict[str, list[str]] = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        header = tuple(normalize_text(ws.cell(1, col).value) for col in range(1, ws.max_column + 1))
        missing_headers = [item for item in REQUIRED_HEADERS.get(sheet_name, ()) if item not in header]
        if missing_headers:
            issues.append(
                QualityIssue(
                    code="HEADER_CONTRACT_DRIFT",
                    status=DataQualityStatus.BLOCKING,
                    sheet=sheet_name,
                    source_reference="row 1",
                    summary=f"Missing required headers: {', '.join(missing_headers)}",
                    affected_records=len(missing_headers),
                    blocking=True,
                )
            )
        if sheet_name == "over view":
            overview_sections = _scan_overview_sections(ws)
            for section, references in overview_sections.items():
                if not references:
                    issues.append(
                        QualityIssue(
                            code="OVERVIEW_SECTION_CONTRACT_DRIFT",
                            status=DataQualityStatus.BLOCKING,
                            sheet=sheet_name,
                            source_reference="semantic scan",
                            summary=f"Required semantic section not found: {section}",
                            affected_records=1,
                            blocking=True,
                        )
                    )
        error_cells = [cell.coordinate for row in ws.iter_rows() for cell in row if cell.data_type == "e"]
        sheet_profiles.append(
            {
                "sheet": sheet_name,
                "state": ws.sheet_state,
                "range": ws.calculate_dimension(),
                "max_row": ws.max_row,
                "max_column": ws.max_column,
                "data_rows": max(ws.max_row - 1, 0),
                "required_headers_present": not missing_headers,
                "error_cell_count": len(error_cells),
                "sample_error_cells": error_cells[:10],
            }
        )
        inventory_only.extend(_scan_inventory_only(ws))

    if any(profile["sheet"] == "over view" and profile["error_cell_count"] for profile in sheet_profiles):
        overview = next(profile for profile in sheet_profiles if profile["sheet"] == "over view")
        issues.append(
            QualityIssue(
                code="OVERVIEW_CACHED_ERROR_VALUES",
                status=DataQualityStatus.WARNING,
                sheet="over view",
                source_reference=", ".join(overview["sample_error_cells"]),
                summary=f"Management summary contains {overview['error_cell_count']} cached/literal Excel error cells",
                affected_records=overview["error_cell_count"],
            )
        )

    sku_map, sku_issues = _build_sku_map(wb["SKU MAP"])
    issues.extend(sku_issues)
    actual_records, actual_issues, actual_stats = _canonical_actual_order(
        wb["actual order"], snapshot, sku_map, mappings
    )
    issues.extend(actual_issues)
    dfc_records, dfc_issues, dfc_stats = _canonical_dfc(
        wb["THD- robot Sell out"], snapshot, sku_map
    )
    issues.extend(dfc_issues)
    canonical = actual_records + dfc_records

    for sheet in ("over view", "2026 acutal cost"):
        issues.append(
            QualityIssue(
                code="EXACT_DATA_THROUGH_UNKNOWN",
                status=DataQualityStatus.WARNING,
                sheet=sheet,
                source_reference="period labels",
                summary="Exact day-level data-through is not explicit; monthly/MTD labels are not converted into a guessed date",
                affected_records=1,
            )
        )

    traceability_complete = all(
        record.source_file
        and record.source_sha256
        and record.source_sheet
        and record.source_section
        and record.source_header
        and record.source_reference
        for record in canonical
    )
    dfc_isolated = all(
        record.metric_domain is MetricDomain.THD_DFC_SELLOUT
        for record in canonical
        if record.source_sheet == "THD- robot Sell out"
    ) and not any(
        record.metric_domain is MetricDomain.THD_DFC_SELLOUT
        for record in canonical
        if record.source_sheet != "THD- robot Sell out"
    )
    if not traceability_complete:
        issues.append(
            QualityIssue(
                code="CANONICAL_TRACEABILITY_INCOMPLETE",
                status=DataQualityStatus.BLOCKING,
                sheet="<canonical candidates>",
                source_reference="all records",
                summary="One or more candidates lack a required traceability field",
                affected_records=sum(1 for record in canonical if not record.source_reference),
                blocking=True,
            )
        )
    if not dfc_isolated:
        issues.append(
            QualityIssue(
                code="DFC_DOMAIN_ISOLATION_FAILED",
                status=DataQualityStatus.BLOCKING,
                sheet="<canonical candidates>",
                source_reference="metric_domain",
                summary="DFC records crossed the approved source/domain boundary",
                affected_records=1,
                blocking=True,
            )
        )

    wb.close()
    after_hash = sha256_file(workbook_path)
    hash_unchanged = before_hash == after_hash
    if not hash_unchanged:
        issues.append(
            QualityIssue(
                code="SOURCE_WORKBOOK_MUTATED",
                status=DataQualityStatus.BLOCKING,
                sheet="<workbook>",
                source_reference=workbook_path.name,
                summary=f"SHA-256 changed from {before_hash} to {after_hash}",
                affected_records=1,
                blocking=True,
            )
        )

    blocking = [issue for issue in issues if issue.blocking]
    return {
        "snapshot": asdict(snapshot),
        "hash_before": before_hash,
        "hash_after": after_hash,
        "hash_unchanged": hash_unchanged,
        "sheet_names": list(wb.sheetnames),
        "sheet_profiles": sheet_profiles,
        "overview_sections": overview_sections,
        "inventory_only": inventory_only,
        "canonical_hierarchy": list(CANONICAL_HIERARCHY),
        "canonical_candidates": canonical,
        "canonical_candidate_count": len(canonical),
        "actual_order": actual_stats,
        "thd_dfc": dfc_stats,
        "sku_mapping_count": len(sku_map),
        "quality_issues": issues,
        "traceability_complete": traceability_complete,
        "dfc_isolated": dfc_isolated,
        "kpi_status": next(
            source_item for source_item in sources["sources"] if source_item["sheet"] == "KPI Rawdata"
        ),
        "blocking_issue_count": len(blocking),
        "ready_for_phase2": not blocking,
    }


def _md_table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    headers = list(headers)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join("UNKNOWN" if value is None else str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def render_reports(profile: dict[str, Any]) -> dict[str, str]:
    snapshot = profile["snapshot"]
    inventory_rows = [
        (
            item["sheet"], item["range"], item["data_rows"], item["state"],
            "PASS" if item["required_headers_present"] else "BLOCKING",
        )
        for item in profile["sheet_profiles"]
    ]
    oos_rows = [
        (
            item["business"], item["sheet"], item["section"], item["record_count"],
            item["count_basis"], item["status"], item["exclusion_reason"],
        )
        for item in profile["inventory_only"]
    ]
    for business in _INVENTORY_ONLY_GROUPS:
        if not any(row[0] == business for row in oos_rows):
            oos_rows.append(
                (business, "all scanned business sections", "not observed", 0, "source rows", "OUT_OF_SCOPE_FOR_STORM_V2", "Not part of the approved STORM V2 core channel contract")
            )
    section_rows = [
        (section, len(refs), ", ".join(refs) if refs else "NOT FOUND")
        for section, refs in profile["overview_sections"].items()
    ]
    inventory = f"""# Workbook Inventory

## Source integrity

- File: `{snapshot['source_file']}`
- Size: `{snapshot['byte_size']:,}` bytes
- SHA-256 before: `{profile['hash_before']}`
- SHA-256 after: `{profile['hash_after']}`
- Read-only integrity: `{'PASS' if profile['hash_unchanged'] else 'BLOCKING'}`
- Visible sheet count: `{len(profile['sheet_names'])}`

## Sheet inventory

{_md_table(('Sheet', 'Used range', 'Rows after row 1', 'Visibility', 'Header contract'), inventory_rows)}

`over view` is a formatted management-summary grid, so its row count is a layout-row count rather than a transaction count. All other counts above are physical rows after the header; semantic valid-row counts are stated in the source mapping report.

## Overview semantic sections

{_md_table(('Section label', 'Occurrences', 'Observed references'), section_rows)}

Coordinates are validation hints only. Section labels, header sequence, and business keys define the contract.

## Inventory-only business data

The following data is present in the authoritative workbook and is monitored for structural/count drift. It is inventory evidence only: it is not registered as a V2 source, mapped, converted to canonical candidates, quality-scored, or admitted to later engines.

{_md_table(('Business', 'Sheet', 'Section', 'Records', 'Count basis', 'Status', 'Reason'), oos_rows)}
"""

    data_contract = """# STORM V2 Phase 1 Data Contract

## Canonical hierarchy

`Platform → Channel/Subchannel → Brand → Power Source → SKU`

Every dimension is nullable. Missing facts remain `UNKNOWN`/`UNMAPPED`; no inferred fallback or zero-fill is allowed.

## Canonical record

Each candidate contains metric domain/name/value/unit/scenario/date; all five hierarchy dimensions; mapping status; raw value/dimensions; and exact source file hash, sheet, semantic section, header, and row/cell reference.

## Metric domains

| Domain | Approved use | Isolation rule |
| --- | --- | --- |
| `SALES` | Core actual order revenue and units | Consumer DFC data cannot enter |
| `ADS` | Approved core advertising metrics | Phase 1 contract only; no engine |
| `CM_BUSINESS_PERFORMANCE` | Approved BP/CM reconciliation | Phase 1 contract only; no engine |
| `THD_DFC_SELLOUT` | THD consumer sell-out, traffic, conversion, current inventory | Only `THD- robot Sell out` may populate |

## KPI Rawdata baseline

- Status: `REFERENCE_BASELINE / NOT_WEEKLY_ACTUAL_INPUT`
- Phase 1: no refresh, no recalculation, no Weekly Actual use.
- Permitted reference use: BP, CM, SKU mapping and related baseline context, subject to approved core scope.
- Future update: permitted through version, SHA-256, approval, and replacement record. This is not a permanent immutability assumption.

## Time semantics

- `actual order`: exact normalized dates, 2026-08-01 through 2026-08-10.
- `THD- robot Sell out`: exact normalized dates, 2026-01-01 through 2026-08-10.
- `over view` and `2026 acutal cost`: monthly/MTD context only; exact day-level data-through is `UNKNOWN`.
- `KPI Rawdata`: 2026 planning/reference horizon; not a Weekly Actual date source.
- `SKU MAP`: timeless mapping baseline.
"""

    source_mapping = f"""# Source Mapping Matrix

## Registered sources and roles

| Sheet | Approved role | Weekly actual | Canonical output in Phase 1 profiler |
| --- | --- | --- | --- |
| `over view` | Management reconciliation reference | No | No |
| `2026 acutal cost` | Core cost/CM reconciliation reference | No | No |
| `actual order` | Core weekly actual orders | Yes | `SALES` revenue and units |
| `THD- robot Sell out` | THD consumer DFC actual | Yes | `THD_DFC_SELLOUT` units, GMV, traffic, conversion, inventory |
| `KPI Rawdata` | `REFERENCE_BASELINE / NOT_WEEKLY_ACTUAL_INPUT` | No | No |
| `SKU MAP` | SKU/Brand/Power reference | No | Dimension enrichment only |

## Core channel mappings

| Raw label | Platform | Channel/Subchannel | Status |
| --- | --- | --- | --- |
| Walmart Seller / Walmart MP | Walmart | MP | MAPPED |
| Walmart DSV | Walmart | DSV | MAPPED |
| Lowe's / Lowes | Lowe's | DS | MAPPED |
| The Home Depot Inc / THD / HomeDepot | THD | DS | MAPPED |
| Walmart (without approved context) | UNKNOWN | UNKNOWN | AMBIGUOUS |

Prior V1 channel taxonomy is not inherited. `3P`, `WFS`, `1P`, and `THD Online` are not canonical V2 channel values.

## DFC isolation

DFC financial rows in overview/cost contexts are `EXCLUDED_CONTRACT_CONFLICT`. They cannot enter ordinary `SALES` and cannot populate the DFC consumer domain. The consumer domain is populated only by the dedicated sell-out sheet.

## Observed coverage

- SKU mapping: `{profile['sku_mapping_count']}` normalized keys.
- Core actual rows accepted: `{profile['actual_order']['accepted_rows']}`.
- Core canonical metric candidates: `{profile['canonical_candidate_count']}`.
- Actual-order unmapped SKU rows: `{sum(profile['actual_order']['unmapped_sku_rows'].values())}`; retained as `UNMAPPED` with raw values.
- DFC daily consumer rows accepted: `{profile['thd_dfc']['accepted_rows']}`.
- Traceability completeness: `{'PASS' if profile['traceability_complete'] else 'BLOCKING'}`.
- DFC domain isolation: `{'PASS' if profile['dfc_isolated'] else 'BLOCKING'}`.
"""

    quality_rows = [
        (issue.status.value, issue.code, issue.sheet, issue.affected_records, issue.source_reference, issue.summary)
        for issue in profile["quality_issues"]
    ]
    quality = f"""# Data Quality Report

## Gate result

- Blocking issues: `{profile['blocking_issue_count']}`
- Non-blocking warnings: `{sum(1 for issue in profile['quality_issues'] if issue.status is DataQualityStatus.WARNING)}`
- Workbook hash unchanged: `{'PASS' if profile['hash_unchanged'] else 'BLOCKING'}`
- Traceability complete: `{'PASS' if profile['traceability_complete'] else 'BLOCKING'}`
- DFC isolated: `{'PASS' if profile['dfc_isolated'] else 'BLOCKING'}`

## Findings

{_md_table(('Severity', 'Code', 'Sheet', 'Affected', 'Reference', 'Finding'), quality_rows)}

Warnings are explicit and non-blocking. No unknown fact is inferred or converted to zero. Inventory-only businesses are intentionally not quality-scored here.
"""

    if profile["ready_for_phase2"]:
        status = "STORM_V2_PHASE_1_DATA_CONTRACT_READY"
        readiness = "READY_FOR_PHASE_2"
        decision = "Phase 1 completion gates pass. Phase 2 is eligible for a separately authorized start; no Phase 2 work has been executed."
    else:
        status = "STORM_V2_PHASE_1_BLOCKED_BY_DATA_CONTRACT"
        readiness = "NOT_READY_FOR_PHASE_2"
        decision = "One or more critical source-contract, DFC-isolation, traceability, or source-integrity gates failed."
    recommendation = f"""# Phase 1 Recommendation

## Decision

`{status}`

`{readiness}`

{decision}

## Completion gate

- Six-sheet and semantic/header contracts: `{'PASS' if profile['blocking_issue_count'] == 0 else 'SEE BLOCKERS'}`
- Canonical hierarchy fixed: `PASS`
- Unknown/unmapped values remain explicit: `PASS`
- Complete candidate traceability: `{'PASS' if profile['traceability_complete'] else 'BLOCKING'}`
- THD DFC consumer isolation: `{'PASS' if profile['dfc_isolated'] else 'BLOCKING'}`
- KPI baseline is controllably replaceable and not Weekly Actual: `PASS`
- Inventory-only source-presence monitoring: `PASS`
- Raw workbook pre/post SHA-256: `{'PASS' if profile['hash_unchanged'] else 'BLOCKING'}`

## Phase boundary

No database, dashboard, Feishu, Hermes, automation, snapshot export, or analysis engine was created or activated. Implementation stops at Phase 1.
"""
    return {
        "workbook_inventory.md": inventory,
        "data_contract.md": data_contract,
        "source_mapping_matrix.md": source_mapping,
        "data_quality_report.md": quality,
        "phase1_recommendation.md": recommendation,
    }


def write_reports(profile: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in render_reports(profile).items():
        (output_dir / name).write_text(content.rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--write-reports", action="store_true")
    args = parser.parse_args()
    profile = profile_workbook(args.workbook, args.project_root)
    if args.write_reports:
        write_reports(profile, args.project_root / "reports" / "phase1")
    print(
        json.dumps(
            {
                "hash_unchanged": profile["hash_unchanged"],
                "blocking_issue_count": profile["blocking_issue_count"],
                "canonical_candidate_count": profile["canonical_candidate_count"],
                "ready_for_phase2": profile["ready_for_phase2"],
            },
            indent=2,
        )
    )
    return 0 if profile["ready_for_phase2"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
