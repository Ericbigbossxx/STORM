"""Append-only Phase 2 canonical snapshot builder.

Phase 1 remains the workbook reader and source-contract authority.  This module
only assigns the approved Phase 2 source roles and persists normalized records.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

from .data_contract import MappingStatus, MetricDomain
from .normalization import as_number, normalize_sku, normalize_text
from .workbook_profiler import profile_workbook


PHASE2_CONTRACT_VERSION = "2.0.0-sales"
SNAPSHOT_FIELDS = (
    "record_id",
    "snapshot_date",
    "period_start",
    "period_end",
    "data_through",
    "platform",
    "channel",
    "subchannel",
    "brand",
    "power_source",
    "sku",
    "metric_domain",
    "metric_name",
    "metric_value",
    "unit",
    "scenario",
    "record_role",
    "source_file",
    "source_sha256",
    "source_sheet",
    "source_section",
    "source_header",
    "source_reference",
    "mapping_status",
    "data_quality_status",
    "raw_value",
    "raw_dimensions",
    "order_number",
)


@dataclass(slots=True)
class Phase2Data:
    snapshot_id: str
    snapshot_date: date
    source: dict[str, Any]
    sales_facts: list[dict[str, Any]]
    dfc_facts: list[dict[str, Any]]
    reference_baseline: list[dict[str, Any]]
    quality_issues: list[dict[str, Any]]
    source_roles: list[dict[str, str]]
    profile_stats: dict[str, Any]

    @property
    def canonical_records(self) -> list[dict[str, Any]]:
        return self.sales_facts + self.dfc_facts + self.reference_baseline


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_iso)


def _channel_contract(project_root: Path) -> dict[str, dict[str, str]]:
    mappings = json.loads((project_root / "config" / "mappings.yaml").read_text(encoding="utf-8"))
    return {
        (normalize_text(raw) or "").casefold(): canonical
        for raw, canonical in mappings["channels"].items()
        if normalize_text(raw)
    }


def _base_row(
    *,
    snapshot_date: date,
    data_through: str | None,
    record: Any,
    metric_name: str | None = None,
    record_role: str = "FACT",
    data_quality_status: str = "VALID",
) -> dict[str, Any]:
    period = _iso(record.period_date)
    name = metric_name or record.metric_name
    record_id = f"{record.source_sheet}:{record.source_reference}:{name}"
    dimensions = dict(record.raw_dimensions)
    order_number = dimensions.get("order_number")
    return {
        "record_id": record_id,
        "snapshot_date": snapshot_date.isoformat(),
        "period_start": period,
        "period_end": period,
        "data_through": data_through,
        "platform": record.platform or "UNKNOWN",
        "channel": record.channel_subchannel or "UNKNOWN",
        "subchannel": None,
        "brand": record.brand or "UNKNOWN",
        "power_source": record.power_source or "UNKNOWN",
        "sku": record.sku or "UNKNOWN",
        "metric_domain": record.metric_domain.value,
        "metric_name": name,
        "metric_value": record.metric_value,
        "unit": record.metric_unit,
        "scenario": record.scenario,
        "record_role": record_role,
        "source_file": record.source_file,
        "source_sha256": record.source_sha256,
        "source_sheet": record.source_sheet,
        "source_section": record.source_section,
        "source_header": record.source_header,
        "source_reference": record.source_reference,
        "mapping_status": record.mapping_status.value,
        "data_quality_status": data_quality_status,
        "raw_value": record.raw_value,
        "raw_dimensions": _json(dimensions),
        "order_number": order_number,
    }


def _sales_rows(profile: dict[str, Any], snapshot_date: date) -> list[dict[str, Any]]:
    data_through = profile["actual_order"]["data_through"]
    result: list[dict[str, Any]] = []
    for record in profile["canonical_candidates"]:
        if record.source_sheet != "actual order" or record.metric_domain is not MetricDomain.SALES:
            continue
        raw_date = record.raw_dimensions.get("date")
        warning = record.mapping_status is not MappingStatus.MAPPED or isinstance(raw_date, str)
        result.append(
            _base_row(
                snapshot_date=snapshot_date,
                data_through=data_through,
                record=record,
                data_quality_status="WARNING" if warning else "VALID",
            )
        )
    return result


def _dfc_rows(profile: dict[str, Any], snapshot_date: date) -> list[dict[str, Any]]:
    candidates = [
        record
        for record in profile["canonical_candidates"]
        if record.source_sheet == "THD- robot Sell out"
        and record.source_section == "consumer daily sell-out"
        and record.metric_domain is MetricDomain.THD_DFC_SELLOUT
    ]
    by_source: dict[str, dict[str, float | int | None]] = {}
    for record in candidates:
        name = "gmv" if record.source_header == "GMV" else record.metric_name
        by_source.setdefault(record.source_reference, {})[name] = record.metric_value
    anomalies = {
        ref
        for ref, metrics in by_source.items()
        if (metrics.get("units") or 0) > 0 and metrics.get("gmv") == 0
    }
    data_through = profile["thd_dfc"]["data_through"]
    result: list[dict[str, Any]] = []
    for record in candidates:
        name = "gmv" if record.source_header == "GMV" else record.metric_name
        warning = record.mapping_status is not MappingStatus.MAPPED or record.source_reference in anomalies
        row = _base_row(
            snapshot_date=snapshot_date,
            data_through=data_through,
            record=record,
            metric_name=name,
            data_quality_status="WARNING" if warning else "VALID",
        )
        if name == "gmv":
            row["unit"] = "USD"
        result.append(row)
    return result


def _header_map(ws) -> dict[str, int]:
    result: dict[str, int] = {}
    for column, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1)), 1):
        label = normalize_text(cell.value)
        if label and label not in result:
            result[label] = column
    return result


def _reference_rows(
    workbook_path: Path,
    project_root: Path,
    snapshot_date: date,
    source_sha256: str,
    actual_data_through: str,
) -> list[dict[str, Any]]:
    actual_date = date.fromisoformat(actual_data_through)
    month_start = actual_date.replace(day=1)
    month_end = actual_date.replace(day=calendar.monthrange(actual_date.year, actual_date.month)[1])
    channels = _channel_contract(project_root)
    wb = load_workbook(workbook_path, read_only=True, data_only=True, keep_links=True)
    ws = wb["KPI Rawdata"]
    headers = _header_map(ws)
    result: list[dict[str, Any]] = []
    for row_number, values in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        get_value = lambda header: values[headers[header] - 1]
        raw_customer = get_value("Customer")
        customer_key = (normalize_text(raw_customer) or "").casefold()
        channel = channels.get(customer_key)
        if not channel:
            continue
        year = as_number(get_value("Year"))
        month = as_number(get_value("Month-INT"))
        if year != actual_date.year or month != actual_date.month:
            continue
        raw_sku = get_value("SKU")
        sku = normalize_sku(raw_sku)
        brand = normalize_text(get_value("Brand"))
        power_source = normalize_text(get_value("Power Source"))
        mapped = bool(sku and brand and power_source)
        dimensions = {
            "customer": raw_customer,
            "sku": raw_sku,
            "month": get_value("Month"),
            "month_int": month,
            "year": year,
        }
        for source_header, metric_name, unit in (
            ("TTL amount", "revenue", "USD"),
            ("Qty", "units", "unit"),
        ):
            raw_value = get_value(source_header)
            metric_value = as_number(raw_value)
            status = "VALID" if mapped and metric_value is not None else "WARNING"
            result.append(
                {
                    "record_id": f"KPI Rawdata:{row_number}:{metric_name}",
                    "snapshot_date": snapshot_date.isoformat(),
                    "period_start": month_start.isoformat(),
                    "period_end": month_end.isoformat(),
                    "data_through": None,
                    "platform": channel["platform"],
                    "channel": channel["channel_subchannel"],
                    "subchannel": None,
                    "brand": brand or "UNKNOWN",
                    "power_source": power_source or "UNKNOWN",
                    "sku": sku or "UNKNOWN",
                    "metric_domain": "SALES",
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "unit": unit,
                    "scenario": "BP",
                    "record_role": "REFERENCE",
                    "source_file": workbook_path.name,
                    "source_sha256": source_sha256,
                    "source_sheet": "KPI Rawdata",
                    "source_section": "monthly reference baseline",
                    "source_header": source_header,
                    "source_reference": f"{row_number}:{row_number}",
                    "mapping_status": "MAPPED" if mapped else "UNMAPPED",
                    "data_quality_status": status,
                    "raw_value": raw_value,
                    "raw_dimensions": _json(dimensions),
                    "order_number": None,
                }
            )
    wb.close()
    return result


def build_phase2_data(
    workbook_path: Path,
    project_root: Path | None = None,
    snapshot_date: date | None = None,
) -> Phase2Data:
    workbook_path = workbook_path.resolve()
    project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    snapshot_date = snapshot_date or date.today()
    profile = profile_workbook(workbook_path, project_root)
    if not profile["ready_for_phase2"]:
        raise ValueError("Phase 1 source contract is not ready for Phase 2")
    source = dict(profile["snapshot"])
    source["captured_at"] = _iso(source["captured_at"])
    source["modified_at"] = _iso(source["modified_at"])
    snapshot_id = f"{snapshot_date.isoformat()}_{profile['hash_before'][:12].lower()}"
    sales = _sales_rows(profile, snapshot_date)
    dfc = _dfc_rows(profile, snapshot_date)
    reference = _reference_rows(
        workbook_path,
        project_root,
        snapshot_date,
        profile["hash_before"],
        profile["actual_order"]["data_through"],
    )
    source_roles = [
        {"sheet": "actual order", "section": "weekly order rows", "role": "FACT"},
        {"sheet": "THD- robot Sell out", "section": "A:G consumer daily sell-out", "role": "FACT"},
        {"sheet": "KPI Rawdata", "section": "monthly baseline", "role": "REFERENCE"},
        {"sheet": "SKU MAP", "section": "mapping baseline", "role": "REFERENCE"},
        {"sheet": "over view", "section": "management summary", "role": "RECONCILIATION_ONLY"},
        {"sheet": "2026 acutal cost", "section": "cost and CM", "role": "EXCLUDED"},
        {"sheet": "THD- robot Sell out", "section": "J:W inventory/month blocks", "role": "EXCLUDED"},
    ]
    return Phase2Data(
        snapshot_id=snapshot_id,
        snapshot_date=snapshot_date,
        source=source,
        sales_facts=sales,
        dfc_facts=dfc,
        reference_baseline=reference,
        quality_issues=[asdict(issue) for issue in profile["quality_issues"]],
        source_roles=source_roles,
        profile_stats={"actual_order": profile["actual_order"], "thd_dfc": profile["thd_dfc"]},
    )


def _csv_text(records: Iterable[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=SNAPSHOT_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({field: record.get(field) for field in SNAPSHOT_FIELDS})
    return buffer.getvalue()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def _coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    source_rows = {record["source_reference"] for record in records}
    mapped_rows = {
        record["source_reference"] for record in records if record["mapping_status"] == "MAPPED"
    }
    return {
        "source_rows": len(source_rows),
        "mapped_rows": len(mapped_rows),
        "unmapped_rows": len(source_rows - mapped_rows),
        "mapped_pct": (len(mapped_rows) / len(source_rows)) if source_rows else None,
    }


def write_snapshot(
    data: Phase2Data,
    snapshot_root: Path,
    *,
    manifest_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot_root = snapshot_root.resolve()
    target = snapshot_root / data.snapshot_id
    csv_payloads = {
        "canonical_records.csv": _csv_text(data.canonical_records),
        "sales_facts.csv": _csv_text(data.sales_facts),
        "thd_dfc_sellout_facts.csv": _csv_text(data.dfc_facts),
        "reference_baseline.csv": _csv_text(data.reference_baseline),
    }
    record_counts = {
        "canonical_records": len(data.canonical_records),
        "sales_facts": len(data.sales_facts),
        "sales_source_rows": len({row["source_reference"] for row in data.sales_facts}),
        "dfc_facts": len(data.dfc_facts),
        "dfc_source_rows": len({row["source_reference"] for row in data.dfc_facts}),
        "reference_baseline": len(data.reference_baseline),
    }
    manifest: dict[str, Any] = {
        "snapshot_id": data.snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file": data.source["source_file"],
        "source_size": data.source["byte_size"],
        "source_sha256": data.source["sha256"],
        "record_counts": record_counts,
        "sales_data_through": data.profile_stats["actual_order"]["data_through"],
        "dfc_sellout_data_through": data.profile_stats["thd_dfc"]["data_through"],
        "mapping_coverage": {
            "sales": _coverage(data.sales_facts),
            "thd_dfc": _coverage(data.dfc_facts),
            "reference_baseline": _coverage(data.reference_baseline),
        },
        "warning_count": sum(1 for issue in data.quality_issues if str(issue["status"]) == "WARNING"),
        "parser_version": PHASE2_CONTRACT_VERSION,
        "contract_version": PHASE2_CONTRACT_VERSION,
        "source_roles": data.source_roles,
        "file_sha256": {name: _sha256_text(text) for name, text in csv_payloads.items()},
    }
    if manifest_extra:
        manifest.update(manifest_extra)

    if target.exists():
        existing = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in csv_payloads.items():
            path = target / name
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                raise FileExistsError(f"Append-only snapshot collision with different content: {target}")
        if existing.get("source_sha256") != manifest["source_sha256"] or existing.get("record_counts") != record_counts:
            raise FileExistsError(f"Append-only snapshot manifest collision: {target}")
        existing["reused"] = True
        return existing

    snapshot_root.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=False, exist_ok=False)
    for name, text in csv_payloads.items():
        (target / name).write_text(text, encoding="utf-8", newline="")
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=_iso) + "\n",
        encoding="utf-8",
    )
    manifest["reused"] = False
    return manifest
