"""Common sell-in sales engine for the approved Phase 2 channel contract."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Sequence


HIERARCHY = ("platform", "channel", "brand", "power_source", "sku")
APPROVED_PLATFORM_CHANNELS = {
    ("Walmart", "MP"),
    ("Walmart", "DSV"),
    ("Lowe's", "DS"),
    ("THD", "DS"),
}


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


def _sum_or_none(values: Iterable[Any]) -> float | None:
    numbers = [number for value in values if (number := _number(value)) is not None]
    return sum(numbers) if numbers else None


def _validate_group_by(group_by: Sequence[str]) -> tuple[str, ...]:
    result = tuple(group_by)
    if any(field not in HIERARCHY for field in result):
        raise ValueError(f"group_by must be drawn from {HIERARCHY}")
    if len(set(result)) != len(result):
        raise ValueError("group_by fields must be unique")
    return result


def _actual_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for record in records:
        if record.get("record_role") != "FACT" or record.get("scenario") != "ACTUAL":
            continue
        if record.get("metric_domain") != "SALES":
            continue
        pair = (record.get("platform"), record.get("channel"))
        if pair not in APPROVED_PLATFORM_CHANNELS:
            continue
        result.append(record)
    return result


def aggregate_sales(
    records: Iterable[dict[str, Any]],
    group_by: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Aggregate revenue, units, distinct orders, and ASP at any hierarchy cut."""

    group_by = _validate_group_by(group_by)
    buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in _actual_records(records):
        key = tuple(record.get(field) for field in group_by)
        bucket = buckets.setdefault(
            key,
            {
                "revenue": [],
                "units": [],
                "orders": set(),
                "dates": [],
                "trace_record_ids": set(),
                "source_references": set(),
            },
        )
        metric = record.get("metric_name")
        if metric in ("revenue", "units"):
            bucket[metric].append(record.get("metric_value"))
        order_number = record.get("order_number")
        if order_number not in (None, ""):
            bucket["orders"].add(str(order_number))
        if parsed := _date(record.get("period_start")):
            bucket["dates"].append(parsed)
        if record.get("record_id"):
            bucket["trace_record_ids"].add(record["record_id"])
        if record.get("source_reference"):
            bucket["source_references"].add(record["source_reference"])

    output: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        revenue = _sum_or_none(bucket["revenue"])
        units = _sum_or_none(bucket["units"])
        asp = (revenue / units) if revenue is not None and units not in (None, 0) else None
        row = {field: value for field, value in zip(group_by, key)}
        row.update(
            {
                "period_start": min(bucket["dates"]).isoformat() if bucket["dates"] else None,
                "period_end": max(bucket["dates"]).isoformat() if bucket["dates"] else None,
                "data_through": max(bucket["dates"]).isoformat() if bucket["dates"] else None,
                "actual_sales": revenue,
                "units": units,
                "orders": len(bucket["orders"]) if bucket["orders"] else None,
                "asp": asp,
                "trace_record_count": len(bucket["trace_record_ids"]),
                "trace_record_ids": sorted(bucket["trace_record_ids"]),
                "source_references": sorted(bucket["source_references"]),
            }
        )
        output.append(row)
    total_sales = sum(row["actual_sales"] or 0 for row in output)
    for row in output:
        row["sales_contribution"] = (
            row["actual_sales"] / total_sales if total_sales and row["actual_sales"] is not None else None
        )
    return sorted(
        output,
        key=lambda row: tuple(str(row.get(field) or "") for field in group_by),
    )


def attach_baseline(
    actual_rows: list[dict[str, Any]],
    baseline_records: Iterable[dict[str, Any]],
    group_by: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach BP only when dimensions, metric, and exact period are compatible."""

    group_by = _validate_group_by(group_by)
    baseline: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for record in baseline_records:
        if record.get("record_role") != "REFERENCE" or record.get("scenario") != "BP":
            continue
        if record.get("metric_domain") != "SALES" or record.get("metric_name") != "revenue":
            continue
        key = (
            record.get("period_start"),
            record.get("period_end"),
            *(record.get(field) for field in group_by),
        )
        value = _number(record.get("metric_value"))
        if value is not None:
            baseline[key].append(value)

    result: list[dict[str, Any]] = []
    matched_count = 0
    matched_sales = 0.0
    total_sales = sum(_number(row.get("actual_sales")) or 0 for row in actual_rows)
    for row in actual_rows:
        item = dict(row)
        key = (
            row.get("period_start"),
            row.get("period_end"),
            *(row.get(field) for field in group_by),
        )
        values = baseline.get(key)
        if not values:
            item.update(
                {
                    "bp": None,
                    "gap": None,
                    "attainment": None,
                    "gap_contribution": None,
                    "bp_status": "BP_NOT_AVAILABLE",
                    "bp_warning": "No exact-period compatible baseline",
                }
            )
        else:
            bp = sum(values)
            actual = _number(row.get("actual_sales"))
            gap = (actual - bp) if actual is not None else None
            item.update(
                {
                    "bp": bp,
                    "gap": gap,
                    "attainment": (actual / bp) if actual is not None and bp != 0 else None,
                    "gap_contribution": None,
                    "bp_status": "MATCHED",
                    "bp_warning": "BP is zero; attainment suppressed" if bp == 0 else None,
                }
            )
            matched_count += 1
            matched_sales += actual or 0
        result.append(item)
    total_gap = sum(_number(row.get("gap")) or 0 for row in result if row.get("gap") is not None)
    if total_gap:
        for row in result:
            if row.get("gap") is not None:
                row["gap_contribution"] = row["gap"] / total_gap
    coverage = {
        "matched_group_count": matched_count,
        "unmatched_group_count": len(result) - matched_count,
        "matched_actual_sales_pct": matched_sales / total_sales if total_sales else None,
        "unmatched_actual_sales_pct": (total_sales - matched_sales) / total_sales if total_sales else None,
        "comparison_period_start": actual_rows[0].get("period_start") if actual_rows else None,
        "comparison_period_end": actual_rows[0].get("period_end") if actual_rows else None,
    }
    return result, coverage


def performance_rankings(rows: Iterable[dict[str, Any]], limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    rows = list(rows)
    by_sales = sorted(rows, key=lambda row: _number(row.get("actual_sales")) or 0, reverse=True)
    matched = [row for row in rows if row.get("bp_status") == "MATCHED" and row.get("gap") is not None]
    return {
        "top_sales_contributors": by_sales[:limit],
        "lowest_sales_contributors": list(reversed(by_sales[-limit:])),
        "top_positive_bp_gaps": sorted(matched, key=lambda row: row["gap"], reverse=True)[:limit],
        "top_negative_bp_gaps": sorted(matched, key=lambda row: row["gap"])[:limit],
    }


def reconcile_common_sales(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Reconcile retained raw values to normalized facts by platform/channel/date."""

    buckets: dict[tuple[str, str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for record in _actual_records(records):
        metric = record.get("metric_name")
        if metric not in ("revenue", "units"):
            continue
        key = (
            record["platform"],
            record["channel"],
            record["period_start"],
            metric,
        )
        raw = _number(record.get("raw_value"))
        normalized = _number(record.get("metric_value"))
        if raw is not None:
            buckets[key][0] += raw
        if normalized is not None:
            buckets[key][1] += normalized
    rows = []
    for (platform, channel, period, metric), (raw, normalized) in sorted(buckets.items()):
        rows.append(
            {
                "platform": platform,
                "channel": channel,
                "date": period,
                "metric": metric,
                "raw_total": raw,
                "normalized_total": normalized,
                "difference": normalized - raw,
            }
        )
    return {
        "status": "PASS" if all(abs(row["difference"]) < 1e-9 for row in rows) else "FAIL",
        "group_count": len(rows),
        "max_abs_difference": max((abs(row["difference"]) for row in rows), default=0.0),
        "rows": rows,
    }


def reconcile_hierarchy(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    facts = list(records)
    total = aggregate_sales(facts)[0] if aggregate_sales(facts) else {"actual_sales": None, "units": None}
    rows = []
    for depth in range(1, len(HIERARCHY) + 1):
        group_by = HIERARCHY[:depth]
        aggregate = aggregate_sales(facts, group_by)
        sales = sum(_number(row.get("actual_sales")) or 0 for row in aggregate)
        units = sum(_number(row.get("units")) or 0 for row in aggregate)
        rows.append(
            {
                "level": "/".join(group_by),
                "sales_total": sales,
                "units_total": units,
                "sales_difference": sales - (_number(total.get("actual_sales")) or 0),
                "units_difference": units - (_number(total.get("units")) or 0),
            }
        )
    return {
        "status": "PASS"
        if all(abs(row["sales_difference"]) < 1e-9 and abs(row["units_difference"]) < 1e-9 for row in rows)
        else "FAIL",
        "rows": rows,
    }
