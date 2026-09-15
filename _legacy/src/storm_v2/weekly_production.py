"""Contract-gated weekly STORM production.

This module deliberately treats source SHA-256 as traceability.  A changed
workbook is accepted only when its contract and the existing business controls
continue to pass; historical published snapshots are never overwritten.
"""

from __future__ import annotations

import calendar
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .integrated_review import generate_phase4
from .comparison import compare_package_to_previous
from .phase5r import build_phase5r_package
from .sku_bp import extract_sku_bp, reconcile_bp
from .snapshot import build_phase2_data, write_snapshot
from .workbook_profiler import EXPECTED_SHEETS, REQUIRED_HEADERS, profile_workbook, sha256_file
from .ytd import extract_ytd_metrics


RAW_SOURCE = "RAW_SALES_DFC"
CM_SOURCE = "CM_BP"
WEEK_PATTERN = re.compile(r"^(\d{4})-W(\d{2})$")
CM_REQUIRED_SHEETS = ("Overview", "KPI Rawdata", "SKU Mapping", "Walmart Seller-WBP", "KPI Trend", "2026 Actual Cost")
CM_REQUIRED_HEADERS = {
    "KPI Rawdata": ("SKU", "Customer", "Month-INT", "Year", "Month", "TTL amount", "Brand", "Power Source"),
    # The authoritative source retains its verified source-header typo.
    "SKU Mapping": ("SKU", "Brand", "Pource Source"),
    "2026 Actual Cost": ("Item", "Channel", "Brand", "MTD", "YTD"),
}


class WeeklyProductionBlocked(RuntimeError):
    """Raised when a weekly run must not create or publish a snapshot."""


@dataclass(frozen=True)
class SourceCandidate:
    source_type: str
    path: Path
    sha256: str
    modified_at: str
    period: str | None
    contract: dict[str, Any]


def _headers(sheet: Any) -> set[str]:
    return {str(value).strip() for values in sheet.iter_rows(min_row=1, max_row=1, values_only=True) for value in values if value is not None}


def _workbook_contract(path: Path) -> dict[str, Any]:
    workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        sheets = set(workbook.sheetnames)
        raw_match = set(EXPECTED_SHEETS).issubset(sheets)
        cm_match = set(CM_REQUIRED_SHEETS).issubset(sheets)
        # Check both contracts; a combined workbook may satisfy both.
        contracts: list[dict[str, Any]] = []
        if raw_match:
            missing = {sheet: sorted(set(headers) - _headers(workbook[sheet])) for sheet, headers in REQUIRED_HEADERS.items()}
            contracts.append({
                "source_type": RAW_SOURCE,
                "required_sheet": list(EXPECTED_SHEETS),
                "required_columns": REQUIRED_HEADERS,
                "header_signature": {sheet: sorted(_headers(workbook[sheet])) for sheet in REQUIRED_HEADERS},
                "required_dimensions": ["Platform", "Channel", "Brand", "Power Source", "SKU"],
                "required_metrics": ["Actual Sales", "Units", "THD DFC GMV", "Traffic"],
                "expected_period_structure": "daily Actual Orders and THD DFC dates",
                "business_keys": ["Date", "Channel", "SKU", "Order Number"],
                "allowed_null_behavior": "existing Phase 2 profiler warnings only",
                "missing": {sheet: values for sheet, values in missing.items() if values},
                "compatible": not any(missing.values()),
                "period": None,
            })
        if cm_match:
            missing = {sheet: sorted(set(headers) - _headers(workbook[sheet])) for sheet, headers in CM_REQUIRED_HEADERS.items()}
            period = f"{workbook['Overview']['B2'].value} {workbook['Overview']['B3'].value}"
            contracts.append({
                "source_type": CM_SOURCE,
                "required_sheet": list(CM_REQUIRED_SHEETS),
                "required_columns": CM_REQUIRED_HEADERS,
                "header_signature": {sheet: sorted(_headers(workbook[sheet])) for sheet in CM_REQUIRED_HEADERS},
                "required_dimensions": ["Platform", "Channel", "Brand", "Power Source", "SKU", "Walmart Seller roster"],
                "required_metrics": ["BP", "Actual", "CM", "CM%", "MTD", "YTD"],
                "expected_period_structure": "Overview MTD and 2026 Actual Cost YTD",
                "business_keys": ["Customer", "SKU", "Year", "Month-INT", "Brand", "Power Source"],
                "allowed_null_behavior": "CM/YTD unavailable remains N/A; no inferred values",
                "missing": {sheet: values for sheet, values in missing.items() if values},
                "compatible": not any(missing.values()),
                "period": period,
            })
        if not contracts:
            return {"source_type": None, "compatible": False, "missing": {"workbook": ["does not match a STORM source signature"]}}
        if len(contracts) == 1:
            return contracts[0]
        # Combined workbook satisfies both contracts
        return {"source_type": "COMBINED", "contracts": contracts, "compatible": all(c["compatible"] for c in contracts)}
    finally:
        workbook.close()


def discover_sources(inbox: Path) -> dict[str, SourceCandidate]:
    """Identify exactly one compatible Raw Sales/DFC and CM/BP workbook.

    A single combined workbook that satisfies both contracts is accepted and
    registered under both source roles.
    """
    inbox = inbox.resolve()
    if not inbox.is_dir():
        raise WeeklyProductionBlocked(f"Weekly inbox does not exist: {inbox}")
    candidates: dict[str, list[SourceCandidate]] = {RAW_SOURCE: [], CM_SOURCE: []}
    for path in sorted(inbox.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        contract = _workbook_contract(path)
        if contract["source_type"] == "COMBINED":
            # Combined workbook satisfies both RAW and CM contracts
            file_hash = sha256_file(path)
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            for sub in contract["contracts"]:
                candidates[sub["source_type"]].append(SourceCandidate(
                    source_type=sub["source_type"],
                    path=path,
                    sha256=file_hash,
                    modified_at=modified,
                    period=sub.get("period"),
                    contract=sub,
                ))
        elif contract["source_type"]:
            candidates[contract["source_type"]].append(SourceCandidate(
                source_type=contract["source_type"],
                path=path,
                sha256=sha256_file(path),
                modified_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                period=contract.get("period"),
                contract=contract,
            ))
    errors = []
    selected: dict[str, SourceCandidate] = {}
    for source_type, items in candidates.items():
        if len(items) != 1:
            names = [item.path.name for item in items]
            errors.append(f"{source_type}: expected exactly one compatible candidate, found {len(items)} ({names})")
        else:
            selected[source_type] = items[0]
    if errors:
        raise WeeklyProductionBlocked("DISCOVER BLOCKED: " + "; ".join(errors))
    return selected


def _month_name(month: int) -> str:
    return calendar.month_abbr[month]


def _snapshot_date_for_week(week_key: str) -> date:
    match = WEEK_PATTERN.fullmatch(week_key)
    if not match:
        raise ValueError(f"week_key must be YYYY-Www: {week_key}")
    return date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)


def validate_sources(sources: dict[str, SourceCandidate], project_root: Path) -> dict[str, Any]:
    raw = sources[RAW_SOURCE]
    cm = sources[CM_SOURCE]
    incompatible = [name for name, item in sources.items() if not item.contract["compatible"]]
    if incompatible:
        raise WeeklyProductionBlocked(f"VALIDATE BLOCKED: incompatible source contract(s): {incompatible}")
    profile = profile_workbook(raw.path, project_root)
    actual_cutoff = profile["actual_order"]["data_through"]
    if not profile["ready_for_phase2"]:
        raise WeeklyProductionBlocked("VALIDATE BLOCKED: Raw Sales/DFC Phase 2 contract failed")
    cutoff = date.fromisoformat(actual_cutoff)
    extraction = extract_sku_bp(cm.path, year=cutoff.year, month=cutoff.month)
    bp_reconciliation = reconcile_bp(extraction)
    if bp_reconciliation["status"] not in ("PASS", "SKIP_NO_BASELINE"):
        raise WeeklyProductionBlocked("VALIDATE BLOCKED: Walmart roster or BP hierarchy reconciliation failed")
    return {
        "status": "PASS",
        "raw_profile": {
            "actual_cutoff": actual_cutoff,
            "dfc_cutoff": profile["thd_dfc"]["data_through"],
            "warning_count": len(profile["quality_issues"]),
            "source_sha256": profile["hash_before"],
        },
        "cm_period": cm.period,
        "bp_reconciliation": bp_reconciliation,
        "source_compatibility": {name: item.contract["compatible"] for name, item in sources.items()},
    }


def _failed_report(project_root: Path, week_key: str, message: str) -> Path:
    target = project_root / "data" / "failed_runs" / f"{week_key}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"week_key": week_key, "status": "FAILED", "reason": message}, indent=2) + "\n", encoding="utf-8")
    return target


def _all_reconciliation_statuses_pass(value: Any) -> bool:
    if isinstance(value, dict):
        if "status" in value and value["status"] not in ("PASS", "SKIP_NO_BASELINE"):
            return False
        return all(_all_reconciliation_statuses_pass(child) for child in value.values())
    if isinstance(value, list):
        return all(_all_reconciliation_statuses_pass(child) for child in value)
    return True


def set_latest(project_root: Path, snapshot_id: str) -> Path:
    """Update only the mutable pointer; it never changes a snapshot itself."""
    pointer = project_root / "data" / "published" / "latest.json"
    manifest = project_root / "data" / "snapshots" / snapshot_id / "manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(manifest)
    pointer.write_text(json.dumps({"snapshot_id": snapshot_id, "manifest_path": str(manifest)}, indent=2) + "\n", encoding="utf-8")
    return pointer


def run_weekly_production(project_root: Path, week_key: str, inbox: Path) -> dict[str, Any]:
    """Run DISCOVER → VALIDATE → INGEST → RECONCILE → SNAPSHOT → PUBLISH."""
    project_root = project_root.resolve()
    try:
        sources = discover_sources(inbox)
        validation = validate_sources(sources, project_root)
    except WeeklyProductionBlocked as exc:
        report = _failed_report(project_root, week_key, str(exc))
        return {"status": "FAILED", "week_key": week_key, "failed_report": str(report), "reason": str(exc)}

    snapshot_date = _snapshot_date_for_week(week_key)
    raw = sources[RAW_SOURCE]
    cm = sources[CM_SOURCE]
    phase2 = build_phase2_data(raw.path, project_root, snapshot_date)
    normalized_manifest = write_snapshot(phase2, project_root / "data" / "snapshots")
    normalized_dir = project_root / "data" / "snapshots" / normalized_manifest["snapshot_id"]
    working = project_root / "data" / "weekly_runs" / week_key
    phase4_dir = working / "phase4"
    phase4 = generate_phase4(raw.path, project_root, snapshot_date=snapshot_date, report_dir=phase4_dir)
    if not _all_reconciliation_statuses_pass(phase4["reconciliation"]):
        report = _failed_report(project_root, week_key, "RECONCILE BLOCKED: Actual/DFC/CM reconciliation failed")
        return {"status": "FAILED", "week_key": week_key, "failed_report": str(report)}
    through_month = date.fromisoformat(validation["raw_profile"]["actual_cutoff"]).month
    ytd = extract_ytd_metrics(cm.path, year=snapshot_date.year, through_month=through_month)
    package = build_phase5r_package(
        bp_workbook=cm.path,
        actual_snapshot_csv=normalized_dir / "sales_facts.csv",
        snapshot_manifest=normalized_dir / "manifest.json",
        phase4_json=phase4_dir / "weekly_business_review.json",
        year=snapshot_date.year,
        month=through_month,
        visual_ready=True,
        ytd_metrics=ytd,
    )
    if package["reconciliation"]["status"] != "PASS":
        report = _failed_report(project_root, week_key, "RECONCILE BLOCKED: package reconciliation failed")
        return {"status": "FAILED", "week_key": week_key, "failed_report": str(report)}
    package_path = working / "phase5r_package.json"
    working.mkdir(parents=True, exist_ok=True)
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    from scripts.build_phase6_snapshot import build_snapshot

    wow = compare_package_to_previous(project_root, package, week_key=week_key)
    manifest = build_snapshot(
        project_root,
        snapshot_date.isoformat(),
        package_path=package_path,
        source_paths=[raw.path, cm.path],
        manifest_overrides={
            "sales_cutoff": validation["raw_profile"]["actual_cutoff"],
            "cm_period": f"{_month_name(date.fromisoformat(validation['raw_profile']['actual_cutoff']).month)} MTD",
            "week_key": week_key,
            "production_status": "PASS",
            "production_validation": validation,
            "wow": wow,
            "ytd": ytd,
            "actual_source_provenance": "WEEKLY_NORMALIZED_PHASE2_SNAPSHOT",
            "source_exception": "NONE: weekly source SHA-256 is recorded for traceability; compatibility and business controls passed.",
        },
    )
    pointer = set_latest(project_root, manifest["snapshot_id"])
    return {
        "status": "STORM_V2_PHASE_7_WEEKLY_PRODUCTION_UI_READY",
        "week_key": week_key,
        "sources": {name: {"filename": item.path.name, "sha256": item.sha256, "modified_at": item.modified_at, "period": item.period} for name, item in sources.items()},
        "validation": validation,
        "snapshot": manifest,
        "latest": str(pointer),
    }
