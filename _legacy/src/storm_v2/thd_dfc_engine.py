"""Independent THD DFC consumer sell-out engine."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable, Sequence


DFC_HIERARCHY = ("brand", "power_source", "sku")


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fact_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("record_role") == "FACT"
        and record.get("scenario") == "ACTUAL"
        and record.get("metric_domain") == "THD_DFC_SELLOUT"
        and record.get("platform") == "THD"
        and record.get("channel") == "DFC"
    ]


def _atomic_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in _fact_records(records):
        reference = record["source_reference"]
        bucket = buckets.setdefault(
            reference,
            {
                "source_reference": reference,
                "date": _date(record.get("period_start")),
                "brand": record.get("brand"),
                "power_source": record.get("power_source"),
                "sku": record.get("sku"),
                "metrics": {},
                "raw_metrics": {},
                "trace_record_ids": set(),
            },
        )
        metric = record.get("metric_name")
        bucket["metrics"][metric] = _number(record.get("metric_value"))
        bucket["raw_metrics"][metric] = _number(record.get("raw_value"))
        if record.get("record_id"):
            bucket["trace_record_ids"].add(record["record_id"])
    result = []
    for bucket in buckets.values():
        units = bucket["metrics"].get("units")
        gmv = bucket["metrics"].get("gmv")
        bucket["positive_units_zero_gmv"] = bool((units or 0) > 0 and gmv == 0)
        bucket["trace_record_ids"] = sorted(bucket["trace_record_ids"])
        result.append(bucket)
    return sorted(result, key=lambda row: (row["date"] or date.min, row["source_reference"]))


def aggregate_dfc(
    records: Iterable[dict[str, Any]],
    group_by: Sequence[str] = (),
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[dict[str, Any]]:
    group_by = tuple(group_by)
    if any(field not in DFC_HIERARCHY for field in group_by) or len(set(group_by)) != len(group_by):
        raise ValueError(f"group_by must contain unique fields from {DFC_HIERARCHY}")
    buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
    for atomic in _atomic_rows(records):
        current_date = atomic["date"]
        if current_date is None:
            continue
        if period_start and current_date < period_start:
            continue
        if period_end and current_date > period_end:
            continue
        key = tuple(atomic.get(field) for field in group_by)
        bucket = buckets.setdefault(
            key,
            {
                "dates": [],
                "units": [],
                "gmv": [],
                "traffic": [],
                "anomaly_count": 0,
                "trace_record_ids": set(),
                "source_references": set(),
            },
        )
        bucket["dates"].append(current_date)
        for metric in ("units", "gmv", "traffic"):
            value = atomic["metrics"].get(metric)
            if value is not None:
                bucket[metric].append(value)
        bucket["anomaly_count"] += int(atomic["positive_units_zero_gmv"])
        bucket["trace_record_ids"].update(atomic["trace_record_ids"])
        bucket["source_references"].add(atomic["source_reference"])

    output = []
    for key, bucket in buckets.items():
        units = sum(bucket["units"]) if bucket["units"] else None
        gmv = sum(bucket["gmv"]) if bucket["gmv"] else None
        traffic = sum(bucket["traffic"]) if bucket["traffic"] else None
        asp = (
            gmv / units
            if gmv is not None and units not in (None, 0) and bucket["anomaly_count"] == 0
            else None
        )
        row = {field: value for field, value in zip(group_by, key)}
        row.update(
            {
                "period_start": min(bucket["dates"]).isoformat(),
                "period_end": max(bucket["dates"]).isoformat(),
                "data_through": max(bucket["dates"]).isoformat(),
                "units": units,
                "gmv": gmv,
                "traffic": traffic,
                "asp": asp,
                "asp_status": (
                    "SUPPRESSED_POSITIVE_UNITS_ZERO_GMV"
                    if bucket["anomaly_count"]
                    else "UNAVAILABLE_ZERO_UNITS"
                    if units == 0
                    else "AVAILABLE"
                ),
                "positive_units_zero_gmv_count": bucket["anomaly_count"],
                "trace_record_count": len(bucket["trace_record_ids"]),
                "trace_record_ids": sorted(bucket["trace_record_ids"]),
                "source_references": sorted(bucket["source_references"]),
            }
        )
        output.append(row)
    total_gmv = sum(row["gmv"] or 0 for row in output)
    for row in output:
        row["gmv_contribution"] = row["gmv"] / total_gmv if total_gmv and row["gmv"] is not None else None
    return sorted(output, key=lambda row: tuple(str(row.get(field) or "") for field in group_by))


def _date_range(start: date, end: date) -> set[date]:
    return {start + timedelta(days=offset) for offset in range((end - start).days + 1)}


def build_dfc_review(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    facts = list(records)
    atomic = _atomic_rows(facts)
    dates = {row["date"] for row in atomic if row["date"] is not None}
    if not dates:
        raise ValueError("No THD DFC facts are available")
    data_through = max(dates)
    mtd_start = data_through.replace(day=1)
    mtd = aggregate_dfc(facts, ("sku",), period_start=mtd_start, period_end=data_through)
    daily = []
    for current_date in sorted(dates):
        row = aggregate_dfc(facts, (), period_start=current_date, period_end=current_date)[0]
        row["date"] = current_date.isoformat()
        daily.append(row)

    recent_start = data_through - timedelta(days=6)
    previous_end = recent_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    complete_windows = _date_range(previous_start, data_through).issubset(dates)
    recent_by_sku: dict[str, dict[str, Any]] = {}
    previous_by_sku: dict[str, dict[str, Any]] = {}
    if complete_windows:
        recent_by_sku = {
            row["sku"]: row
            for row in aggregate_dfc(facts, ("sku",), period_start=recent_start, period_end=data_through)
        }
        previous_by_sku = {
            row["sku"]: row
            for row in aggregate_dfc(facts, ("sku",), period_start=previous_start, period_end=previous_end)
        }
    for row in mtd:
        recent = recent_by_sku.get(row["sku"])
        previous = previous_by_sku.get(row["sku"])
        row["recent_7d_units"] = recent.get("units") if recent else None
        row["recent_7d_gmv"] = recent.get("gmv") if recent else None
        row["previous_7d_units"] = previous.get("units") if previous else None
        row["previous_7d_gmv"] = previous.get("gmv") if previous else None
        previous_gmv = previous.get("gmv") if previous else None
        recent_gmv = recent.get("gmv") if recent else None
        row["gmv_7d_change"] = (
            (recent_gmv - previous_gmv) / previous_gmv
            if recent_gmv is not None and previous_gmv not in (None, 0)
            else None
        )
    mtd_sorted = sorted(mtd, key=lambda row: row["gmv"] or 0, reverse=True)
    total = aggregate_dfc(facts, (), period_start=mtd_start, period_end=data_through)[0]
    return {
        "data_through": data_through.isoformat(),
        "mtd_period_start": mtd_start.isoformat(),
        "mtd_total": total,
        "mtd_by_sku": mtd_sorted,
        "daily_trend": daily,
        "recent_window": {
            "available": complete_windows,
            "recent_start": recent_start.isoformat(),
            "recent_end": data_through.isoformat(),
            "previous_start": previous_start.isoformat(),
            "previous_end": previous_end.isoformat(),
        },
        "leaders": mtd_sorted[:5],
        "lowest_contributors": sorted(mtd, key=lambda row: row["gmv"] or 0)[:5],
    }


def reconcile_dfc(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    atomic = _atomic_rows(records)
    raw_units = sum(row["raw_metrics"].get("units") or 0 for row in atomic)
    normalized_units = sum(row["metrics"].get("units") or 0 for row in atomic)
    raw_gmv = sum(row["raw_metrics"].get("gmv") or 0 for row in atomic)
    normalized_gmv = sum(row["metrics"].get("gmv") or 0 for row in atomic)
    result = {
        "record_count": len(atomic),
        "raw_units": raw_units,
        "normalized_units": normalized_units,
        "units_difference": normalized_units - raw_units,
        "raw_gmv": raw_gmv,
        "normalized_gmv": normalized_gmv,
        "gmv_difference": normalized_gmv - raw_gmv,
        "positive_units_zero_gmv_count": sum(row["positive_units_zero_gmv"] for row in atomic),
    }
    result["status"] = (
        "PASS"
        if abs(result["units_difference"]) < 1e-9 and abs(result["gmv_difference"]) < 1e-9
        else "FAIL"
    )
    return result
