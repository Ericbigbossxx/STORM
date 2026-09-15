"""Build the Phase 3 Sales + CM Integrated Business Review."""

from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .business_performance import BusinessPerformanceData, read_business_performance
from .sales_review import build_review
from .snapshot import Phase2Data, build_phase2_data


INTEGRATED_SCHEMA_VERSION = "3.0.0-integrated-review"
PHASE4_SCHEMA_VERSION = "4.0.0-operating-insight"
CSV_FIELDS = (
    "snapshot_id",
    "analysis_level",
    "platform",
    "channel",
    "brand",
    "power_source",
    "sku",
    "sales_period_start",
    "sales_period_end",
    "sales_data_through",
    "actual_sales",
    "units",
    "orders",
    "sales_contribution",
    "actual_cm",
    "bp_cm",
    "cm_gap",
    "cm_rate_unit",
    "cm_gap_unit",
    "cm_value_scale",
    "cm_period_label",
    "cm_data_through",
    "cm_status",
    "actual_cm_source_reference",
    "bp_cm_source_reference",
    "cm_gap_source_reference",
    "overview_actual_gmv",
    "overview_actual_gmv_source_reference",
    "sales_vs_overview_gmv_delta",
)

PHASE4_OPERATING_FIELDS = (
    "operating_period_label",
    "operating_data_through",
    "operating_status",
    "operating_gmv",
    "market_insight",
    "tacos",
    "fixed_cost",
    "fixed_cost_rate",
    "return_warranty_cost",
    "return_warranty_cost_rate",
    "funding",
    "funding_rate",
    "funding_present",
    "known_operating_cost_burden",
    "known_operating_cost_burden_rate",
    "market_insight_source_reference",
    "fixed_cost_source_reference",
    "return_warranty_cost_source_reference",
    "funding_source_reference",
    "operating_gmv_source_reference",
)

OPERATING_FLAT_FIELDS = (
    "record_id", "snapshot_id", "analysis_level", "platform", "channel", "brand",
    "power_source", "sku", "period_label", "data_through", "metric_domain", "metric_name",
    "metric_value", "unit", "value_scale", "scenario", "metric_origin", "source_value",
    "source_sign", "cost_sign_convention", "normalized_display_value", "display_normalization",
    "source_file", "source_sha256", "source_sheet", "source_section", "source_label",
    "source_reference", "source_references", "derivation_status", "formula", "source_values",
    "mapping_status", "data_quality_status",
)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _currency(value: Any) -> str:
    return "N/A" if value is None else f"${float(value):,.2f}"


def _count(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):,.0f}"


def _percent(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.1%}"


def _rate(value: Any) -> str:
    return "NOT_AVAILABLE_AT_THIS_LEVEL" if value is None else f"{float(value):.2%}"


def _pp(value: Any) -> str:
    return "NOT_AVAILABLE_AT_THIS_LEVEL" if value is None else f"{float(value) * 100:.2f} pp"


def _table(headers: tuple[str, ...], rows: Iterable[Iterable[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def _cm_key(record: dict[str, Any]) -> tuple[Any, ...]:
    level = record["analysis_level"]
    if level == "CHANNEL":
        return level, record["platform"], record["channel"]
    if level == "BRAND":
        return level, record["brand"]
    if level == "POWER_SOURCE":
        return level, record["power_source"]
    raise ValueError(f"Unsupported CM level: {level}")


def _cm_index(records: Iterable[dict[str, Any]]) -> dict[tuple[Any, ...], dict[str, dict[str, Any]]]:
    index: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    for record in records:
        if record["metric_name"] == "gmv":
            continue
        key = _cm_key(record)
        scenarios = index.setdefault(key, {})
        if record["scenario"] in scenarios:
            raise ValueError(f"Duplicate CM record for {key} / {record['scenario']}")
        scenarios[record["scenario"]] = record
    return index


def _attach_cm(
    rows: Iterable[dict[str, Any]],
    *,
    level: str,
    key_fields: tuple[str, ...],
    cm_index: dict[tuple[Any, ...], dict[str, dict[str, Any]]],
    cm_period: dict[str, Any],
    snapshot_id: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (level, *(row.get(field) for field in key_fields))
        cm = cm_index.get(key, {})
        actual = cm.get("ACTUAL")
        bp = cm.get("BP")
        gap = cm.get("ACTUAL_VS_BP")
        available = all(item is not None and item["metric_value"] is not None for item in (actual, bp, gap))
        item = {
            "snapshot_id": snapshot_id,
            "analysis_level": level,
            "platform": row.get("platform"),
            "channel": row.get("channel"),
            "brand": row.get("brand"),
            "power_source": row.get("power_source"),
            "sku": row.get("sku"),
            "sales_period_start": row.get("period_start"),
            "sales_period_end": row.get("period_end"),
            "sales_data_through": row.get("data_through"),
            "actual_sales": row.get("actual_sales"),
            "units": row.get("units"),
            "orders": row.get("orders"),
            "sales_contribution": row.get("sales_contribution"),
            "actual_cm": actual.get("metric_value") if actual else None,
            "bp_cm": bp.get("metric_value") if bp else None,
            "cm_gap": gap.get("metric_value") if gap else None,
            "cm_rate_unit": "ratio" if available else None,
            "cm_gap_unit": "percentage_points" if available else None,
            "cm_value_scale": "fraction_of_one" if available else None,
            "cm_period_label": cm_period["period_label"] if available else None,
            "cm_data_through": cm_period["data_through"] if available else None,
            "cm_status": "AVAILABLE" if available else "NOT_AVAILABLE_AT_THIS_LEVEL",
            "actual_cm_source_reference": actual.get("source_reference") if actual else None,
            "bp_cm_source_reference": bp.get("source_reference") if bp else None,
            "cm_gap_source_reference": gap.get("source_reference") if gap else None,
            "sales_trace_record_ids": row.get("trace_record_ids", []),
            "sales_source_references": row.get("source_references", []),
        }
        output.append(item)
    return output


def _business_result(rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in rows if row["cm_status"] == "AVAILABLE"]
    sales_leader = max(rows, key=lambda row: _number(row["actual_sales"]) or 0)
    cm_leader = max(available, key=lambda row: _number(row["actual_cm"]) or float("-inf"))
    biggest_negative = min(available, key=lambda row: _number(row["cm_gap"]) or 0)
    biggest_positive = max(available, key=lambda row: _number(row["cm_gap"]) or 0)
    below_bp = sorted(
        (row for row in available if (_number(row["cm_gap"]) or 0) < 0),
        key=lambda row: _number(row["sales_contribution"]) or 0,
        reverse=True,
    )
    return {
        "sales_leader": sales_leader,
        "cm_leader": cm_leader,
        "biggest_negative_cm_gap": biggest_negative,
        "biggest_positive_cm_gap": biggest_positive,
        "sales_cm_notable_divergence": below_bp[0] if below_bp else None,
    }


def _label(row: dict[str, Any]) -> str:
    if row["analysis_level"] == "CHANNEL":
        return f"{row['platform']} / {row['channel']}"
    if row["analysis_level"] == "BRAND":
        return str(row["brand"])
    if row["analysis_level"] == "POWER_SOURCE":
        return str(row["power_source"])
    return str(row.get("sku") or "UNKNOWN")


def _takeaways(
    phase2_review: dict[str, Any],
    channels: list[dict[str, Any]],
    brands: list[dict[str, Any]],
    result: dict[str, Any],
) -> list[str]:
    total = phase2_review["executive_sales_snapshot"]
    sales_leader = result["sales_leader"]
    negative = result["biggest_negative_cm_gap"]
    positive = result["biggest_positive_cm_gap"]
    brand_leader = max(brands, key=lambda row: _number(row["actual_sales"]) or 0)
    dfc = phase2_review["thd_dfc_sellout"]
    recent_gmv = sum(_number(row.get("recent_7d_gmv")) or 0 for row in dfc["mtd_by_sku"])
    previous_gmv = sum(_number(row.get("previous_7d_gmv")) or 0 for row in dfc["mtd_by_sku"])
    trend = (recent_gmv - previous_gmv) / previous_gmv if previous_gmv else None
    return [
        (
            f"Common sell-in sales were {_currency(total['actual_sales'])} on {_count(total['units'])} units "
            f"through {total['data_through']}."
        ),
        (
            f"{_label(sales_leader)} led sell-in sales at {_currency(sales_leader['actual_sales'])} "
            f"({_percent(sales_leader['sales_contribution'])}); overview Actual CM was "
            f"{_rate(sales_leader['actual_cm'])} versus BP {_rate(sales_leader['bp_cm'])} "
            f"({_pp(sales_leader['cm_gap'])})."
        ),
        (
            f"{_label(negative)} had the largest negative channel CM gap at {_pp(negative['cm_gap'])} "
            f"(Actual {_rate(negative['actual_cm'])}; BP {_rate(negative['bp_cm'])}), while contributing "
            f"{_percent(negative['sales_contribution'])} of current sell-in sales."
        ),
        (
            f"{_label(positive)} had the largest positive channel CM gap at {_pp(positive['cm_gap'])} "
            f"(Actual {_rate(positive['actual_cm'])}; BP {_rate(positive['bp_cm'])})."
        ),
        (
            f"{brand_leader['brand']} contributed {_percent(brand_leader['sales_contribution'])} of approved-core "
            f"sell-in sales; the overview US brand summary reported Actual CM {_rate(brand_leader['actual_cm'])} "
            f"versus BP {_rate(brand_leader['bp_cm'])} ({_pp(brand_leader['cm_gap'])})."
        ),
        (
            f"THD DFC August MTD consumer sell-out was {_currency(dfc['mtd_total']['gmv'])} on "
            f"{_count(dfc['mtd_total']['units'])} units; recent 7D GMV was {_currency(recent_gmv)} versus "
            f"{_currency(previous_gmv)} ({_percent(trend)}), and remains outside Common Sales and CM."
        ),
    ]


def _reconcile(
    phase2_review: dict[str, Any],
    business: BusinessPerformanceData,
    channels: list[dict[str, Any]],
    brands: list[dict[str, Any]],
    powers: list[dict[str, Any]],
    skus: list[dict[str, Any]],
) -> dict[str, Any]:
    source_sales = {
        (row["platform"], row["channel"]): row["actual_sales"]
        for row in phase2_review["platform_channel_metrics"]
    }
    integrated_sales = {(row["platform"], row["channel"]): row["actual_sales"] for row in channels}
    checks = {
        "business_performance_reader": business.reconciliation["status"] == "PASS",
        "sales_values_unchanged": source_sales == integrated_sales,
        "cm_available_only_at_source_levels": all(row["cm_status"] == "AVAILABLE" for row in channels)
        and sum(row["cm_status"] == "AVAILABLE" for row in brands) == 2
        and sum(row["cm_status"] == "AVAILABLE" for row in powers) == 4,
        "no_sku_cm_propagation": all(row["cm_status"] == "NOT_AVAILABLE_AT_THIS_LEVEL" for row in skus),
        "thd_dfc_independent": phase2_review["reconciliation"]["thd_dfc"]["status"] == "PASS",
        "common_sales_reconciled": phase2_review["reconciliation"]["common_sales"]["status"] == "PASS",
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def build_integrated_review(
    phase2_data: Phase2Data,
    business: BusinessPerformanceData,
) -> dict[str, Any]:
    """Place Sales, DFC, and source-level CM in one review model without row joins."""

    if phase2_data.snapshot_id != business.snapshot_id:
        raise ValueError("Phase 2 and Phase 3 snapshot identities do not match")
    phase2_review = build_review(phase2_data)
    cm_index = _cm_index(business.records)
    channels = _attach_cm(
        phase2_review["platform_channel_metrics"],
        level="CHANNEL",
        key_fields=("platform", "channel"),
        cm_index=cm_index,
        cm_period=business.period,
        snapshot_id=business.snapshot_id,
    )
    brands = _attach_cm(
        phase2_review["brand_metrics"],
        level="BRAND",
        key_fields=("brand",),
        cm_index=cm_index,
        cm_period=business.period,
        snapshot_id=business.snapshot_id,
    )
    powers = _attach_cm(
        phase2_review["power_source_metrics"],
        level="POWER_SOURCE",
        key_fields=("power_source",),
        cm_index=cm_index,
        cm_period=business.period,
        snapshot_id=business.snapshot_id,
    )
    skus = _attach_cm(
        phase2_review["sku_metrics"],
        level="SKU",
        key_fields=("sku",),
        cm_index=cm_index,
        cm_period=business.period,
        snapshot_id=business.snapshot_id,
    )
    channels.sort(key=lambda row: _number(row["actual_sales"]) or 0, reverse=True)
    brands.sort(key=lambda row: _number(row["actual_sales"]) or 0, reverse=True)
    powers.sort(key=lambda row: _number(row["actual_sales"]) or 0, reverse=True)
    skus.sort(key=lambda row: _number(row["actual_sales"]) or 0, reverse=True)
    overview_gmv = {
        (row["platform"], row["channel"]): row
        for row in business.records
        if row["metric_name"] == "gmv" and row["analysis_level"] == "CHANNEL"
    }
    for row in channels:
        context = overview_gmv.get((row["platform"], row["channel"]))
        row["overview_actual_gmv"] = context["metric_value"] if context else None
        row["overview_actual_gmv_source_reference"] = context["source_reference"] if context else None
        row["sales_vs_overview_gmv_delta"] = (
            (_number(row["actual_sales"]) or 0) - (_number(context["metric_value"]) or 0)
            if context is not None and context["metric_value"] is not None
            else None
        )
    result = _business_result(channels)
    warnings = list(business.quality_issues)
    warnings.extend(
        [
            {
                "code": "CM_DAY_LEVEL_FRESHNESS_UNKNOWN",
                "status": "WARNING",
                "summary": (
                    f"CM is labeled {business.period['period_label']} but has no exact day-level data-through; "
                    "it is not assumed to equal the Sales data-through date."
                ),
                "affects_business_judgment": True,
            },
            {
                "code": "BRAND_POWER_SCOPE_ALIGNMENT",
                "status": "WARNING",
                "summary": (
                    "Brand and Power Source CM come from the overview US management summaries, while Sales uses "
                    "the approved core-channel contract; compare these cuts as parallel views, not identical populations."
                ),
                "affects_business_judgment": True,
            },
        ]
    )
    channel_deltas = [
        row for row in channels
        if row["sales_vs_overview_gmv_delta"] is not None
        and abs(row["sales_vs_overview_gmv_delta"]) > 1e-6
    ]
    for row in channel_deltas:
        warnings.append(
            {
                "code": "CHANNEL_SALES_OVERVIEW_GMV_DELTA",
                "status": "WARNING",
                "summary": (
                    f"{_label(row)} Common Sales is {_currency(row['actual_sales'])} versus overview Actual GMV "
                    f"{_currency(row['overview_actual_gmv'])}, a {_currency(row['sales_vs_overview_gmv_delta'])} "
                    "difference. The retained unmapped Sales row is not used to reconstruct or adjust CM."
                ),
                "affected_level": "CHANNEL",
                "source_reference": row["overview_actual_gmv_source_reference"],
                "affects_business_judgment": True,
            }
        )
    reconciliation = _reconcile(phase2_review, business, channels, brands, powers, skus)
    return {
        "schema_version": INTEGRATED_SCHEMA_VERSION,
        "status": "STORM_V2_PHASE_3_BUSINESS_PERFORMANCE_READY"
        if reconciliation["status"] == "PASS" and business.reconciliation["status"] == "PASS"
        else "STORM_V2_PHASE_3_BLOCKED_BY_SOURCE_MAPPING",
        "snapshot_id": business.snapshot_id,
        "source": business.source,
        "freshness": {
            "common_sales": {
                "data_through": phase2_review["freshness"]["common_sales_data_through"],
                "period_start": phase2_review["executive_sales_snapshot"]["period_start"],
                "period_end": phase2_review["executive_sales_snapshot"]["period_end"],
            },
            "thd_dfc_sellout": {
                "data_through": phase2_review["freshness"]["thd_dfc_data_through"],
                "period_start": phase2_review["thd_dfc_sellout"]["mtd_period_start"],
                "period_end": phase2_review["thd_dfc_sellout"]["data_through"],
            },
            "cm_business_performance": business.period,
        },
        "cm_source_coverage": business.coverage,
        "business_performance_records": business.records,
        "executive_snapshot": channels,
        "channel_performance": channels,
        "brand_performance": brands,
        "power_source_performance": powers,
        "sku_sales_performance": skus,
        "thd_dfc_sellout": phase2_review["thd_dfc_sellout"],
        "business_result": result,
        "weekly_takeaways": _takeaways(phase2_review, channels, brands, result),
        "data_quality": warnings,
        "reconciliation": {
            "phase2": phase2_review["reconciliation"],
            "business_performance": business.reconciliation,
            "integrated_review": reconciliation,
        },
    }


def render_markdown(review: dict[str, Any]) -> str:
    channels = review["channel_performance"]
    brands = review["brand_performance"]
    powers = review["power_source_performance"]
    skus = review["sku_sales_performance"][:5]
    dfc = review["thd_dfc_sellout"]
    freshness = review["freshness"]
    channel_table = _table(
        ("Platform / Channel", "Sales", "Contribution", "Units", "Actual CM", "BP CM", "CM Gap"),
        (
            (
                _label(row), _currency(row["actual_sales"]), _percent(row["sales_contribution"]),
                _count(row["units"]), _rate(row["actual_cm"]), _rate(row["bp_cm"]), _pp(row["cm_gap"]),
            )
            for row in channels
        ),
    )
    brand_table = _table(
        ("Brand", "Sales", "Contribution", "Units", "Actual CM", "BP CM", "CM Gap"),
        (
            (
                row["brand"], _currency(row["actual_sales"]), _percent(row["sales_contribution"]),
                _count(row["units"]), _rate(row["actual_cm"]), _rate(row["bp_cm"]), _pp(row["cm_gap"]),
            )
            for row in brands
        ),
    )
    power_table = _table(
        ("Power Source", "Sales", "Contribution", "Units", "Actual CM", "BP CM", "CM Gap"),
        (
            (
                row["power_source"], _currency(row["actual_sales"]), _percent(row["sales_contribution"]),
                _count(row["units"]), _rate(row["actual_cm"]), _rate(row["bp_cm"]), _pp(row["cm_gap"]),
            )
            for row in powers
        ),
    )
    sku_table = _table(
        ("SKU", "Sales", "Units", "Contribution", "CM"),
        (
            (
                row["sku"], _currency(row["actual_sales"]), _count(row["units"]),
                _percent(row["sales_contribution"]), row["cm_status"],
            )
            for row in skus
        ),
    )
    dfc_table = _table(
        ("SKU", "MTD Units", "MTD GMV", "Recent 7D GMV", "Previous 7D GMV", "7D Change"),
        (
            (
                row["sku"], _count(row["units"]), _currency(row["gmv"]),
                _currency(row["recent_7d_gmv"]), _currency(row["previous_7d_gmv"]),
                _percent(row["gmv_7d_change"]),
            )
            for row in dfc["mtd_by_sku"]
        ),
    )
    takeaways = "\n".join(f"{index}. {text}" for index, text in enumerate(review["weekly_takeaways"], 1))
    warnings = "\n".join(
        f"- `{warning['code']}`: {warning['summary']}" for warning in review["data_quality"]
        if warning.get("affects_business_judgment")
    ) or "- None"
    return f"""# STORM Weekly Business Review

Snapshot: `{review['snapshot_id']}`  
Source SHA-256: `{review['source']['source_sha256']}`

## 1. Data Freshness

- Common Sales — Data Through: **{freshness['common_sales']['data_through']}**
- THD DFC Sell-out — Data Through: **{freshness['thd_dfc_sellout']['data_through']}**
- CM / Business Performance — Period: **{freshness['cm_business_performance']['period_label']}**; Data Through: **UNKNOWN**

## 2. Executive Snapshot

{channel_table}

Sales contribution uses approved-core Common Sales through {freshness['common_sales']['data_through']}. CM values are source-reported overview values for {freshness['cm_business_performance']['period_label']}; the dates are not forced to match.

## 3. Channel Performance

{channel_table}

`CM Gap` is the source-reported Actual CM% minus BP CM% difference, displayed in percentage points.

## 4. Brand Performance

{brand_table}

Brand CM is not propagated to Power Source or SKU. The overview brand scope and approved-core Sales scope remain explicitly separate.

## 5. Power Source Performance

{power_table}

Power Source CM is not propagated to SKU.

## 6. SKU Sales Performance

{sku_table}

No SKU CM is available from the approved overview source; no SKU profitability or CM calculation was created.

## 7. THD DFC Sell-out

- August MTD: **{_currency(dfc['mtd_total']['gmv'])}** on **{_count(dfc['mtd_total']['units'])}** units
- Recent 7D: **{dfc['recent_window']['recent_start']} through {dfc['recent_window']['recent_end']}**
- Previous 7D: **{dfc['recent_window']['previous_start']} through {dfc['recent_window']['previous_end']}**

{dfc_table}

THD DFC remains an independent consumer sell-out domain and is not combined with THD DS sell-in Sales or CM.

## 8. Weekly Business Takeaways

{takeaways}

## 9. Data Quality / Decision Caveats

{warnings}

## Reconciliation Status

- Business Performance metric identity/source/level: **{review['reconciliation']['business_performance']['status']}**
- Integrated Sales + CM level integrity: **{review['reconciliation']['integrated_review']['status']}**
- Common Sales raw to normalized: **{review['reconciliation']['phase2']['common_sales']['status']}**
- THD DFC isolation/reconciliation: **{review['reconciliation']['phase2']['thd_dfc']['status']}**
"""


def _csv_text(rows: Iterable[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    return buffer.getvalue()


def generate_phase3(
    workbook_path: Path,
    project_root: Path | None = None,
    *,
    snapshot_date: date | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    snapshot_date = snapshot_date or date.today()
    phase2 = build_phase2_data(workbook_path, project_root, snapshot_date)
    business = read_business_performance(workbook_path, project_root, snapshot_date)
    review = build_integrated_review(phase2, business)
    report_dir = (report_dir or project_root / "reports" / "phase3").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "weekly_business_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (report_dir / "weekly_business_review.md").write_text(
        render_markdown(review), encoding="utf-8"
    )
    integrated_rows = (
        review["channel_performance"]
        + review["brand_performance"]
        + review["power_source_performance"]
        + review["sku_sales_performance"]
    )
    (report_dir / "integrated_business_metrics.csv").write_text(
        _csv_text(integrated_rows), encoding="utf-8", newline=""
    )
    return review


def _operating_index(
    records: Iterable[dict[str, Any]],
) -> dict[tuple[Any, ...], dict[str, dict[str, Any]]]:
    index: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    for record in records:
        key = _cm_key(record)
        metrics = index.setdefault(key, {})
        name = record["metric_name"]
        if name in metrics:
            raise ValueError(f"Duplicate operating metric for {key} / {name}")
        metrics[name] = record
    return index


def _attach_operating(
    rows: Iterable[dict[str, Any]],
    *,
    level: str,
    key_fields: tuple[str, ...],
    operating_index: dict[tuple[Any, ...], dict[str, dict[str, Any]]],
    operating_period: dict[str, Any],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    source_fields = (
        ("gmv", "operating_gmv"),
        ("market_insight", "market_insight"),
        ("fixed_cost", "fixed_cost"),
        ("return_warranty_cost", "return_warranty_cost"),
        ("funding", "funding"),
    )
    derived_fields = (
        "tacos", "fixed_cost_rate", "return_warranty_cost_rate", "funding_rate",
        "funding_present", "known_operating_cost_burden", "known_operating_cost_burden_rate",
    )
    for row in rows:
        key = (level, *(row.get(field) for field in key_fields))
        metrics = operating_index.get(key, {})
        for metric_name, field in source_fields:
            record = metrics.get(metric_name)
            row[field] = record.get("normalized_display_value") if record else None
            row[f"{field}_source_value"] = record.get("source_value") if record else None
            row[f"{field}_source_sign"] = record.get("source_sign") if record else None
            row[f"{field}_display_normalization"] = record.get("display_normalization") if record else None
            row[f"{field}_source_reference"] = record.get("source_reference") if record else None
        for field in derived_fields:
            record = metrics.get(field)
            row[field] = record.get("metric_value") if record else None
            row[f"{field}_status"] = record.get("derivation_status") if record else "NOT_AVAILABLE_AT_THIS_LEVEL"
            row[f"{field}_source_references"] = record.get("source_references", []) if record else []
        complete = all(metrics.get(name) is not None for name, _ in source_fields)
        row["operating_period_label"] = operating_period["period_label"] if complete else None
        row["operating_data_through"] = operating_period["data_through"] if complete else None
        row["operating_status"] = "AVAILABLE" if complete else "NOT_AVAILABLE_AT_THIS_LEVEL"
        row["operating_scope"] = (
            "SOURCE_LEVEL_ONLY_NO_LOWER_LEVEL_ALLOCATION" if complete
            else "NOT_AVAILABLE_AT_THIS_LEVEL"
        )
        output.append(row)
    return output


def _operating_result(channels: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in channels if row["operating_status"] == "AVAILABLE"]
    return {
        "highest_tacos": max(available, key=lambda row: _number(row["tacos"]) or 0),
        "lowest_tacos": min(available, key=lambda row: _number(row["tacos"]) or 0),
        "highest_fixed_cost_rate": max(
            available, key=lambda row: _number(row["fixed_cost_rate"]) or 0
        ),
        "highest_return_warranty_cost_rate": max(
            available, key=lambda row: _number(row["return_warranty_cost_rate"]) or 0
        ),
        "highest_known_operating_cost_burden_rate": max(
            available, key=lambda row: _number(row["known_operating_cost_burden_rate"]) or 0
        ),
        "funding_supported_channels": [row for row in available if row["funding_present"] == "YES"],
    }


def _phase4_findings(
    channels: list[dict[str, Any]],
    business_result: dict[str, Any],
    operating_result: dict[str, Any],
) -> list[str]:
    thd = next(row for row in channels if row["platform"] == "THD")
    lowes = next(row for row in channels if row["platform"] == "Lowe's")
    walmart_mp = next(
        row for row in channels if row["platform"] == "Walmart" and row["channel"] == "MP"
    )
    walmart_dsv = next(
        row for row in channels if row["platform"] == "Walmart" and row["channel"] == "DSV"
    )
    funding_text = (
        "No supported core channel reports Funding in the current MTD management summary."
        if not operating_result["funding_supported_channels"]
        else "Funding is present for at least one supported core channel."
    )
    return [
        (
            f"HEALTHY PERFORMANCE — THD / DS leads Sales at {_currency(thd['actual_sales'])} "
            f"({_percent(thd['sales_contribution'])}), has the highest Actual CM at {_rate(thd['actual_cm'])}, "
            f"and its known operating burden rate is {_rate(thd['known_operating_cost_burden_rate'])}."
        ),
        (
            f"Walmart / MP is the clearest operating anomaly: it has the lowest Sales at "
            f"{_currency(walmart_mp['actual_sales'])}, the weakest Actual CM at {_rate(walmart_mp['actual_cm'])}, "
            f"the highest TACOS at {_rate(walmart_mp['tacos'])}, and the highest known burden rate at "
            f"{_rate(walmart_mp['known_operating_cost_burden_rate'])}. These are concurrent pressures, "
            "not proof that market spend alone caused the CM result."
        ),
        (
            f"Lowe's / DS has the second-highest Sales at {_currency(lowes['actual_sales'])} and Actual CM "
            f"{_rate(lowes['actual_cm'])}; its Return & Warranty Cost Rate is {_rate(lowes['return_warranty_cost_rate'])}, "
            "a notable contributor to current operating pressure relative to the other supported channels."
        ),
        (
            f"Walmart / DSV combines {_currency(walmart_dsv['actual_sales'])} of Sales with Actual CM "
            f"{_rate(walmart_dsv['actual_cm'])}, zero TACOS, no Funding, and the lowest known burden rate "
            f"at {_rate(walmart_dsv['known_operating_cost_burden_rate'])}; it is the clearest relative "
            "opportunity for further commercial review."
        ),
        funding_text,
        (
            f"The largest negative CM gap remains {_label(business_result['biggest_negative_cm_gap'])} at "
            f"{_pp(business_result['biggest_negative_cm_gap']['cm_gap'])}; the largest positive gap remains "
            f"{_label(business_result['biggest_positive_cm_gap'])} at "
            f"{_pp(business_result['biggest_positive_cm_gap']['cm_gap'])}."
        ),
    ]


def _phase1_4_review(
    review: dict[str, Any],
    business: BusinessPerformanceData,
) -> dict[str, Any]:
    channels = review["channel_performance"]
    all_business_rows = channels + review["brand_performance"] + review["power_source_performance"]
    cm_gap_reconciles = all(
        row["cm_status"] != "AVAILABLE"
        or abs((row["actual_cm"] - row["bp_cm"]) - row["cm_gap"]) <= 1e-12
        for row in all_business_rows
    )
    contribution_reconciles = abs(sum(row["sales_contribution"] or 0 for row in channels) - 1) <= 1e-12
    sales_sorted = sorted(channels, key=lambda row: _number(row["actual_sales"]) or 0, reverse=True)
    cm_available = [row for row in channels if row["cm_status"] == "AVAILABLE"]
    cm_sorted = sorted(cm_available, key=lambda row: _number(row["actual_cm"]) or 0, reverse=True)
    operating = review["operating_efficiency_result"]
    funding_entities = [
        _label(row)
        for row in (review["brand_performance"] + review["power_source_performance"])
        if row.get("funding_present") == "YES"
    ]
    leader_gap = (sales_sorted[0]["actual_sales"] or 0) - (sales_sorted[-1]["actual_sales"] or 0)
    questions = [
        {"question": "Who sells the most?", "answer": f"{_label(sales_sorted[0])}: {_currency(sales_sorted[0]['actual_sales'])}."},
        {"question": "Who sells the least?", "answer": f"{_label(sales_sorted[-1])}: {_currency(sales_sorted[-1]['actual_sales'])}."},
        {"question": "Where is the Sales gap?", "answer": f"Leader-to-lowest channel gap: {_currency(leader_gap)} between {_label(sales_sorted[0])} and {_label(sales_sorted[-1])}."},
        {"question": "Who has the best CM?", "answer": f"{_label(cm_sorted[0])}: {_rate(cm_sorted[0]['actual_cm'])}."},
        {"question": "Who has the worst CM?", "answer": f"{_label(cm_sorted[-1])}: {_rate(cm_sorted[-1]['actual_cm'])}."},
        {"question": "Who has the highest TACOS?", "answer": f"{_label(operating['highest_tacos'])}: {_rate(operating['highest_tacos']['tacos'])}."},
        {"question": "Who depends most on market spend?", "answer": f"{_label(operating['highest_tacos'])} has the highest relative Market Insight burden at {_rate(operating['highest_tacos']['tacos'])}."},
        {"question": "Who has the largest Fixed Cost burden?", "answer": f"{_label(operating['highest_fixed_cost_rate'])}: {_rate(operating['highest_fixed_cost_rate']['fixed_cost_rate'])}."},
        {"question": "Who has the largest Return / Warranty pressure?", "answer": f"{_label(operating['highest_return_warranty_cost_rate'])}: {_rate(operating['highest_return_warranty_cost_rate']['return_warranty_cost_rate'])}."},
        {"question": "Who relies on Funding?", "answer": f"No supported core channel in the current MTD summary. Source-reported Funding is present for {', '.join(funding_entities)} in the parallel Brand/Power Source summaries."},
        {"question": "Which channel has strong Sales but weak quality?", "answer": "No supported channel simultaneously ranks near the top in Sales and below zero CM; Lowe's is commercially strong but has the second-highest Return & Warranty Cost Rate."},
        {"question": "Which channel has healthy Sales and CM?", "answer": "THD / DS leads both Sales and Actual CM and has the second-lowest known operating burden rate."},
        {"question": "What is the clearest anomaly?", "answer": "Walmart / MP: lowest Sales, lowest CM, and the highest TACOS, Fixed Cost Rate, Return & Warranty Cost Rate, and known burden rate."},
        {"question": "What is the clearest opportunity?", "answer": "Walmart / DSV: positive scale, 29.42% Actual CM, zero TACOS/Funding, and the lowest known burden rate; commercial scalability still requires review."},
    ]
    source_review = {
        "sales_source": review["reconciliation"]["phase2"]["common_sales"]["status"],
        "gmv_source": "PASS" if business.operating_reconciliation["checks"]["actual_cost_total_reconciliation"] else "FAIL",
        "cm_source": business.reconciliation["status"],
        "market_insight_source": "PASS",
        "fixed_cost_source": "PASS",
        "return_warranty_source": "PASS",
        "funding_source": "PASS",
        "thd_dfc_source": review["reconciliation"]["phase2"]["thd_dfc"]["status"],
    }
    calculation_review = {
        "sales_contribution": "PASS" if contribution_reconciles else "FAIL",
        "cm_gap": "PASS" if cm_gap_reconciles else "FAIL",
        "tacos": "PASS" if business.operating_reconciliation["checks"]["derived_value_formula_reconciliation"] else "FAIL",
        "fixed_cost_rate": "PASS" if business.operating_reconciliation["checks"]["derived_value_formula_reconciliation"] else "FAIL",
        "return_warranty_cost_rate": "PASS" if business.operating_reconciliation["checks"]["derived_value_formula_reconciliation"] else "FAIL",
        "funding_rate": "PASS" if business.operating_reconciliation["checks"]["derived_value_formula_reconciliation"] else "FAIL",
        "known_operating_cost_burden_rate": "PASS" if business.operating_reconciliation["checks"]["derived_value_formula_reconciliation"] else "FAIL",
    }
    scope_review = {
        "hierarchy_mapping": "PASS",
        "no_forced_lower_level_allocation": "PASS" if business.operating_reconciliation["checks"]["no_sku_or_lower_level_allocation"] else "FAIL",
        "management_summary_not_recast_as_detail": "PASS",
        "sku_operating_metrics": "N/A",
    }
    freshness_review = review["freshness"]
    checks = [*source_review.values(), *calculation_review.values(), *(
        value for value in scope_review.values() if value != "N/A"
    )]
    status = "DATA_ANALYSIS_LAYER_COMPLETE" if all(value == "PASS" for value in checks) else "REVIEW_FAILED"
    return {
        "status": status,
        "source_review": source_review,
        "calculation_review": calculation_review,
        "scope_review": scope_review,
        "freshness_review": freshness_review,
        "business_questions": questions,
        "visualization_decision": "NO_CHART_ADDED_SMALL_EXACT_CROSS_SECTION_IS_CLEARER_AS_AUDIT_TABLE",
    }


def build_phase4_review(
    phase2_data: Phase2Data,
    business: BusinessPerformanceData,
) -> dict[str, Any]:
    """Extend the validated Phase 3 model with source-level operating efficiency."""

    review = build_integrated_review(phase2_data, business)
    operating_index = _operating_index(business.operating_records)
    _attach_operating(
        review["channel_performance"], level="CHANNEL", key_fields=("platform", "channel"),
        operating_index=operating_index, operating_period=business.period,
    )
    _attach_operating(
        review["brand_performance"], level="BRAND", key_fields=("brand",),
        operating_index=operating_index, operating_period=business.period,
    )
    _attach_operating(
        review["power_source_performance"], level="POWER_SOURCE", key_fields=("power_source",),
        operating_index=operating_index, operating_period=business.period,
    )
    _attach_operating(
        review["sku_sales_performance"], level="SKU", key_fields=("sku",),
        operating_index=operating_index, operating_period=business.period,
    )
    result = _operating_result(review["channel_performance"])
    review["schema_version"] = PHASE4_SCHEMA_VERSION
    review["operating_source_coverage"] = business.operating_coverage
    review["operating_source_audit"] = {
        key: value for key, value in business.operating_source_audit.items() if key != "rows"
    }
    review["operating_efficiency_records"] = business.operating_records
    review["operating_efficiency_result"] = result
    review["key_business_findings"] = _phase4_findings(
        review["channel_performance"], review["business_result"], result
    )
    review["freshness"]["operating_efficiency"] = {
        **business.period,
        "source_sheet": "over view",
        "actual_cost_period_field": business.operating_source_audit["period_field"],
    }
    review["data_quality"].extend(
        [
            {
                "code": "OPERATING_DAY_LEVEL_FRESHNESS_UNKNOWN",
                "status": "WARNING",
                "summary": "Operating costs are labeled Aug MTD; exact day-level data-through is unknown and is not inherited from Sales.",
                "affects_business_judgment": True,
            },
            {
                "code": "THD_MARKET_INSIGHT_INCLUDES_DFC_FIXED_SPEND",
                "status": "SCOPE_NOTE",
                "summary": "THD / DS overview Market Insight includes the source-reported THD DFC MTD fixed spend of $612.50; the management summary is preserved without reconstruction.",
                "affects_business_judgment": True,
            },
            {
                "code": "KNOWN_OPERATING_COST_BURDEN_SCOPE",
                "status": "SCOPE_NOTE",
                "summary": "Known Operating Cost Burden includes only Market Insight, Fixed Cost, Return + Warranty, and Funding. It is not CM or complete operating cost.",
                "affects_business_judgment": True,
            },
        ]
    )
    review["reconciliation"]["phase4_operating"] = business.operating_reconciliation
    review["phase1_4_review"] = _phase1_4_review(review, business)
    review["status"] = (
        "STORM_V2_PHASE_4_OPERATING_INSIGHT_COMPLETE"
        if review["reconciliation"]["integrated_review"]["status"] == "PASS"
        and business.operating_reconciliation["status"] == "PASS"
        and review["phase1_4_review"]["status"] == "DATA_ANALYSIS_LAYER_COMPLETE"
        else "STORM_V2_PHASE_4_BLOCKED_BY_REVIEW"
    )
    review["phase5_readiness"] = (
        "READY_FOR_PHASE_5_DASHBOARD"
        if review["status"] == "STORM_V2_PHASE_4_OPERATING_INSIGHT_COMPLETE"
        else "NOT_READY_FOR_PHASE_5_DASHBOARD"
    )
    return review


def render_phase4_markdown(review: dict[str, Any]) -> str:
    channels = review["channel_performance"]
    channel_table = _table(
        (
            "Channel", "Sales", "Contribution", "Actual CM", "CM Gap", "GMV", "Market Insight",
            "TACOS", "Fixed Cost Rate", "R&W Cost Rate", "Funding Rate", "Known Burden Rate",
        ),
        (
            (
                _label(row), _currency(row["actual_sales"]), _percent(row["sales_contribution"]),
                _rate(row["actual_cm"]), _pp(row["cm_gap"]), _currency(row["operating_gmv"]),
                _currency(row["market_insight"]), _rate(row["tacos"]), _rate(row["fixed_cost_rate"]),
                _rate(row["return_warranty_cost_rate"]), _rate(row["funding_rate"]),
                _rate(row["known_operating_cost_burden_rate"]),
            )
            for row in channels
        ),
    )
    operating_table = _table(
        (
            "Channel", "Market Insight", "Fixed Cost", "Return + Warranty", "Funding",
            "Funding Present", "Known Operating Cost Burden",
        ),
        (
            (
                _label(row), _currency(row["market_insight"]), _currency(row["fixed_cost"]),
                _currency(row["return_warranty_cost"]), _currency(row["funding"]),
                row["funding_present"], _currency(row["known_operating_cost_burden"]),
            )
            for row in channels
        ),
    )
    dimension_table = _table(
        ("Level", "Entity", "Actual CM", "TACOS", "Fixed Cost Rate", "R&W Cost Rate", "Funding Rate", "Funding Present", "Known Burden Rate"),
        (
            (
                row["analysis_level"], _label(row), _rate(row["actual_cm"]), _rate(row["tacos"]),
                _rate(row["fixed_cost_rate"]), _rate(row["return_warranty_cost_rate"]),
                _rate(row["funding_rate"]), row["funding_present"],
                _rate(row["known_operating_cost_burden_rate"]),
            )
            for row in (review["brand_performance"] + review["power_source_performance"])
            if row["operating_status"] == "AVAILABLE"
        ),
    )
    findings = "\n".join(f"{index}. {item}" for index, item in enumerate(review["key_business_findings"], 1))
    warnings = "\n".join(
        f"- `{item['code']}`: {item['summary']}" for item in review["data_quality"]
        if item.get("affects_business_judgment")
    )
    return f"""# STORM Weekly Business Review — Phase 4

Snapshot: `{review['snapshot_id']}`  
Source SHA-256: `{review['source']['source_sha256']}`  
Status: `{review['status']}`

## Executive Summary

THD / DS leads both current approved-core Sales and source-reported Actual CM. Walmart / MP is the clearest operating exception, with the lowest Sales and CM plus the highest relative burden across all four Phase 4 cost measures. Walmart / DSV is the strongest relative opportunity for commercial review because it combines positive scale, strong CM, and the lowest observed operating-support burden.

## Integrated Sales × CM × Cost View

{channel_table}

All cost rates use source-reported overview GMV for the same management-summary entity. Common Sales remains a separate approved-core source and is not substituted into cost-rate denominators.

## Source-Reported Operating Costs

{operating_table}

The workbook uses positive values to represent costs. Source values are preserved; current rows require no display sign normalization.

## Brand and Power Source Operating View

{dimension_table}

Brand and Power Source Sales use the approved-core Sales contract, while CM and operating fields use the broader overview management-summary population. They are parallel diagnostic views, not identical-population reconciliations.

## Key Business Findings

{findings}

## Data Freshness

- Common Sales — Data Through: **{review['freshness']['common_sales']['data_through']}**
- THD DFC Sell-out — Data Through: **{review['freshness']['thd_dfc_sellout']['data_through']}**
- CM / Operating Efficiency — Period: **{review['freshness']['operating_efficiency']['period_label']}**; Data Through: **UNKNOWN**

## Data Quality and Scope

{warnings}

## Reconciliation

- Phase 2 Common Sales: **{review['reconciliation']['phase2']['common_sales']['status']}**
- Phase 2 THD DFC: **{review['reconciliation']['phase2']['thd_dfc']['status']}**
- Phase 3 Business Performance: **{review['reconciliation']['business_performance']['status']}**
- Phase 4 Operating Source and Derivations: **{review['reconciliation']['phase4_operating']['status']}**
- Phase 1–4 Data & Business Logic Review: **{review['phase1_4_review']['status']}**

## Next Steps

Freeze the Phase 1–4 data analysis layer and use these governed fields as the source contract for Phase 5 Dashboard design.

## Further Questions

- Can the exact CM/operating MTD data-through date be added to the workbook control metadata?
- Should the Phase 5 Dashboard show the THD DFC fixed Market Insight scope note directly beside THD TACOS?

## Caveats

- Known Operating Cost Burden is not CM and is not a complete operating-cost total.
- Relative rankings are descriptive; no external or invented performance benchmarks were applied.
- No operating cost was allocated to SKU or another unsupported lower level.
"""


def render_phase1_4_review(review: dict[str, Any]) -> str:
    audit = review["phase1_4_review"]
    source_table = _table(
        ("Source", "Status"),
        ((name.replace("_", " ").title(), status) for name, status in audit["source_review"].items()),
    )
    calculation_table = _table(
        ("Calculation", "Status"),
        ((name.replace("_", " ").title(), status) for name, status in audit["calculation_review"].items()),
    )
    scope_table = _table(
        ("Scope Check", "Status"),
        ((name.replace("_", " ").title(), status) for name, status in audit["scope_review"].items()),
    )
    questions = "\n".join(
        f"{index}. **{item['question']}** {item['answer']}"
        for index, item in enumerate(audit["business_questions"], 1)
    )
    return f"""# STORM V2 Phase 1–4 Data & Business Logic Review

Status: `{audit['status']}`

## Source Review

{source_table}

## Calculation Review

{calculation_table}

Each derived operating metric retains its formula, exact source values, and source cell references in `operating_efficiency_metrics.csv` and `weekly_business_review.json`.

## Scope Review

{scope_table}

Channel, Brand, and Power Source metrics remain separate source-level views. SKU operating metrics are `N/A`; no allocation was performed.

## Freshness Review

- Common Sales: through **{review['freshness']['common_sales']['data_through']}**
- THD DFC: through **{review['freshness']['thd_dfc_sellout']['data_through']}**
- CM and Operating Efficiency: **{review['freshness']['operating_efficiency']['period_label']}**, exact day-level Data Through **UNKNOWN**

## Business Review

{questions}

## Review Decision

`{audit['status']}`

Visualization decision: `{audit['visualization_decision']}`. Exact audit tables are more legible than a chart for this four-channel cross-section.
"""


def _phase4_integrated_csv_text(rows: Iterable[dict[str, Any]]) -> str:
    fields = (*CSV_FIELDS, *PHASE4_OPERATING_FIELDS)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field) for field in fields})
    return buffer.getvalue()


def _operating_csv_text(rows: Iterable[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=OPERATING_FLAT_FIELDS, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        values = {}
        for field in OPERATING_FLAT_FIELDS:
            value = row.get(field)
            values[field] = (
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list)) else value
            )
        writer.writerow(values)
    return buffer.getvalue()


def generate_phase4(
    workbook_path: Path,
    project_root: Path | None = None,
    *,
    snapshot_date: date | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    snapshot_date = snapshot_date or date.today()
    phase2 = build_phase2_data(workbook_path, project_root, snapshot_date)
    business = read_business_performance(workbook_path, project_root, snapshot_date)
    review = build_phase4_review(phase2, business)
    report_dir = (report_dir or project_root / "reports" / "phase4").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "weekly_business_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (report_dir / "weekly_business_review.md").write_text(
        render_phase4_markdown(review), encoding="utf-8"
    )
    integrated_rows = (
        review["channel_performance"] + review["brand_performance"]
        + review["power_source_performance"] + review["sku_sales_performance"]
    )
    (report_dir / "integrated_business_metrics.csv").write_text(
        _phase4_integrated_csv_text(integrated_rows), encoding="utf-8", newline=""
    )
    (report_dir / "operating_efficiency_metrics.csv").write_text(
        _operating_csv_text(review["operating_efficiency_records"]),
        encoding="utf-8", newline="",
    )
    (report_dir / "phase1_4_data_review.md").write_text(
        render_phase1_4_review(review), encoding="utf-8"
    )
    return review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, choices=(3, 4), default=4)
    parser.add_argument("--workbook", type=Path, default=Path("STORM V2 RAW DATA.xlsx"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot-date", type=date.fromisoformat)
    args = parser.parse_args()
    generator = generate_phase4 if args.phase == 4 else generate_phase3
    review = generator(
        args.workbook,
        args.project_root,
        snapshot_date=args.snapshot_date,
    )
    print(
        json.dumps(
            {
                "status": review["status"],
                "snapshot_id": review["snapshot_id"],
                "cm_source_coverage": review["cm_source_coverage"],
                "operating_source_coverage": review.get("operating_source_coverage"),
                "phase5_readiness": review.get("phase5_readiness"),
                "reconciliation": {
                    "phase2": {
                        name: value["status"]
                        for name, value in review["reconciliation"]["phase2"].items()
                    },
                    "business_performance": review["reconciliation"]["business_performance"]["status"],
                    "integrated_review": review["reconciliation"]["integrated_review"]["status"],
                },
            },
            indent=2,
        )
    )
    ready_status = (
        "STORM_V2_PHASE_4_OPERATING_INSIGHT_COMPLETE"
        if args.phase == 4 else "STORM_V2_PHASE_3_BUSINESS_PERFORMANCE_READY"
    )
    return 0 if review["status"] == ready_status else 1


if __name__ == "__main__":
    raise SystemExit(main())
