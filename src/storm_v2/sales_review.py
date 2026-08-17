"""Generate the first source-backed STORM V2 Weekly Sales Review."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .sales_engine import (
    HIERARCHY,
    aggregate_sales,
    attach_baseline,
    performance_rankings,
    reconcile_common_sales,
    reconcile_hierarchy,
)
from .snapshot import Phase2Data, build_phase2_data, write_snapshot
from .thd_dfc_engine import build_dfc_review, reconcile_dfc


BUSINESS_WARNING_CODES = {
    "ACTUAL_ORDER_UNMAPPED_SKU",
    "ACTUAL_ORDER_MIXED_DATE_TYPES",
    "THD_DFC_POSITIVE_UNITS_ZERO_GMV",
}


def _set_analysis_period(rows: Iterable[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        item = dict(row)
        item["period_start"] = start
        item["period_end"] = end
        item["data_through"] = end
        result.append(item)
    return result


def _currency(value: Any) -> str:
    return "N/A" if value is None else f"${float(value):,.2f}"


def _number(value: Any, decimals: int = 0) -> str:
    return "N/A" if value is None else f"{float(value):,.{decimals}f}"


def _percent(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.1%}"


def _label(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    return " / ".join(str(row.get(field) or "UNKNOWN") for field in fields)


def _table(headers: tuple[str, ...], rows: Iterable[Iterable[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def _business_warnings(data: Phase2Data, bp_coverage: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = [
        {
            "code": str(issue["code"]),
            "status": str(issue["status"]),
            "summary": issue["summary"],
            "affected_records": issue["affected_records"],
            "source_reference": issue["source_reference"],
        }
        for issue in data.quality_issues
        if str(issue["code"]) in BUSINESS_WARNING_CODES
    ]
    if bp_coverage["matched_group_count"] == 0:
        warnings.append(
            {
                "code": "BP_NOT_AVAILABLE",
                "status": "WARNING",
                "summary": (
                    "Actual covers 2026-08-01 through 2026-08-10; KPI Rawdata BP covers the full "
                    "2026-08 month. No daily prorating or period substitution was applied."
                ),
                "affected_records": bp_coverage["unmatched_group_count"],
                "source_reference": "KPI Rawdata monthly reference baseline",
            }
        )
    return warnings


def _takeaways(
    total: dict[str, Any],
    platform_rows: list[dict[str, Any]],
    brand_rows: list[dict[str, Any]],
    power_rows: list[dict[str, Any]],
    sku_rows: list[dict[str, Any]],
    dfc: dict[str, Any],
) -> list[str]:
    sales_date = total["data_through"]
    dfc_date = dfc["data_through"]
    platform_leader = max(platform_rows, key=lambda row: row["actual_sales"] or 0)
    brand_leader = max(brand_rows, key=lambda row: row["actual_sales"] or 0)
    power_leader = max(power_rows, key=lambda row: row["actual_sales"] or 0)
    sku_leader = max(sku_rows, key=lambda row: row["actual_sales"] or 0)
    recent_gmv = sum(row.get("recent_7d_gmv") or 0 for row in dfc["mtd_by_sku"])
    previous_gmv = sum(row.get("previous_7d_gmv") or 0 for row in dfc["mtd_by_sku"])
    trend = (recent_gmv - previous_gmv) / previous_gmv if previous_gmv else None
    return [
        (
            f"Common sell-in sales reached {_currency(total['actual_sales'])} on {_number(total['units'])} units "
            f"across {_number(total['orders'])} distinct orders (Data Through {sales_date})."
        ),
        (
            f"{_label(platform_leader, ('platform', 'channel'))} was the largest channel contributor at "
            f"{_currency(platform_leader['actual_sales'])}, {_percent(platform_leader['sales_contribution'])} "
            f"of current sell-in revenue (Data Through {sales_date})."
        ),
        (
            f"{brand_leader['brand']} led brands at {_currency(brand_leader['actual_sales'])}; "
            f"{power_leader['power_source']} led power sources at {_currency(power_leader['actual_sales'])} "
            f"(Data Through {sales_date})."
        ),
        (
            f"{sku_leader['sku']} was the top SKU at {_currency(sku_leader['actual_sales'])}, "
            f"{_percent(sku_leader['sales_contribution'])} of sell-in revenue (Data Through {sales_date})."
        ),
        (
            "BP gap and attainment rankings are unavailable because the only approved BP is full-month August "
            f"while Actual is MTD through {sales_date}; no prorating was performed."
        ),
        (
            f"THD DFC August MTD consumer sell-out was {_currency(dfc['mtd_total']['gmv'])} on "
            f"{_number(dfc['mtd_total']['units'])} units; recent 7D GMV was {_currency(recent_gmv)} "
            f"versus {_currency(previous_gmv)} ({_percent(trend)}) (Data Through {dfc_date})."
        ),
    ]


def build_review(data: Phase2Data) -> dict[str, Any]:
    period_start = data.profile_stats["actual_order"]["data_from"]
    period_end = data.profile_stats["actual_order"]["data_through"]
    total = _set_analysis_period(aggregate_sales(data.sales_facts), period_start, period_end)[0]
    platform = _set_analysis_period(
        aggregate_sales(data.sales_facts, ("platform", "channel")), period_start, period_end
    )
    brands = _set_analysis_period(aggregate_sales(data.sales_facts, ("brand",)), period_start, period_end)
    powers = _set_analysis_period(aggregate_sales(data.sales_facts, ("power_source",)), period_start, period_end)
    skus = _set_analysis_period(aggregate_sales(data.sales_facts, ("sku",)), period_start, period_end)
    platform_bp, _ = attach_baseline(platform, data.reference_baseline, ("platform", "channel"))
    brand_bp, _ = attach_baseline(brands, data.reference_baseline, ("brand",))
    power_bp, _ = attach_baseline(powers, data.reference_baseline, ("power_source",))
    sku_bp, bp_coverage = attach_baseline(skus, data.reference_baseline, ("sku",))
    rankings = performance_rankings(sku_bp)
    dfc = build_dfc_review(data.dfc_facts)
    common_reconciliation = reconcile_common_sales(data.sales_facts)
    hierarchy_reconciliation = reconcile_hierarchy(data.sales_facts)
    dfc_reconciliation = reconcile_dfc(data.dfc_facts)
    warnings = _business_warnings(data, bp_coverage)
    takeaways = _takeaways(total, platform_bp, brand_bp, power_bp, sku_bp, dfc)
    return {
        "freshness": {
            "common_sales_data_through": period_end,
            "thd_dfc_data_through": data.profile_stats["thd_dfc"]["data_through"],
        },
        "executive_sales_snapshot": total,
        "platform_channel_metrics": sorted(platform_bp, key=lambda row: row["actual_sales"] or 0, reverse=True),
        "brand_metrics": sorted(brand_bp, key=lambda row: row["actual_sales"] or 0, reverse=True),
        "power_source_metrics": sorted(power_bp, key=lambda row: row["actual_sales"] or 0, reverse=True),
        "sku_metrics": sorted(sku_bp, key=lambda row: row["actual_sales"] or 0, reverse=True),
        "sku_rankings": rankings,
        "bp_match_coverage": bp_coverage,
        "thd_dfc_sellout": dfc,
        "reconciliation": {
            "common_sales": common_reconciliation,
            "thd_dfc": dfc_reconciliation,
            "hierarchy_rollup": hierarchy_reconciliation,
        },
        "weekly_takeaways": takeaways,
        "warnings": warnings,
    }


def render_markdown(review: dict[str, Any], manifest: dict[str, Any]) -> str:
    total = review["executive_sales_snapshot"]
    freshness = review["freshness"]
    platform_rows = review["platform_channel_metrics"]
    brand_rows = review["brand_metrics"]
    power_rows = review["power_source_metrics"]
    rankings = review["sku_rankings"]
    dfc = review["thd_dfc_sellout"]
    warning_lines = "\n".join(
        f"- `{warning['code']}`: {warning['summary']}" for warning in review["warnings"]
    ) or "- None"
    takeaway_lines = "\n".join(f"{index}. {text}" for index, text in enumerate(review["weekly_takeaways"], 1))
    platform_table = _table(
        ("Platform / Channel", "Actual Sales", "Units", "Orders", "ASP", "BP", "Gap", "Attainment", "Contribution"),
        (
            (
                _label(row, ("platform", "channel")),
                _currency(row["actual_sales"]),
                _number(row["units"]),
                _number(row["orders"]),
                _currency(row["asp"]),
                _currency(row["bp"]),
                _currency(row["gap"]),
                _percent(row["attainment"]),
                _percent(row["sales_contribution"]),
            )
            for row in platform_rows
        ),
    )
    brand_table = _table(
        ("Brand", "Actual Sales", "Units", "BP", "Gap", "Attainment", "Contribution"),
        (
            (
                row["brand"], _currency(row["actual_sales"]), _number(row["units"]), _currency(row["bp"]),
                _currency(row["gap"]), _percent(row["attainment"]), _percent(row["sales_contribution"]),
            )
            for row in brand_rows
        ),
    )
    power_table = _table(
        ("Power Source", "Actual Sales", "Units", "BP", "Gap", "Attainment", "Contribution"),
        (
            (
                row["power_source"], _currency(row["actual_sales"]), _number(row["units"]), _currency(row["bp"]),
                _currency(row["gap"]), _percent(row["attainment"]), _percent(row["sales_contribution"]),
            )
            for row in power_rows
        ),
    )
    sku_table = _table(
        ("SKU", "Actual Sales", "Units", "Contribution", "BP Status"),
        (
            (row["sku"], _currency(row["actual_sales"]), _number(row["units"]), _percent(row["sales_contribution"]), row["bp_status"])
            for row in rankings["top_sales_contributors"]
        ),
    )
    lowest_sku_table = _table(
        ("SKU", "Actual Sales", "Units", "Contribution", "Interpretation"),
        (
            (
                row["sku"], _currency(row["actual_sales"]), _number(row["units"]),
                _percent(row["sales_contribution"]), "Low contribution only; no comparable BP",
            )
            for row in rankings["lowest_sales_contributors"]
        ),
    )
    dfc_table = _table(
        ("SKU", "MTD Units", "MTD GMV", "Recent 7D GMV", "Previous 7D GMV", "7D Change", "ASP Status"),
        (
            (
                row["sku"], _number(row["units"]), _currency(row["gmv"]), _currency(row["recent_7d_gmv"]),
                _currency(row["previous_7d_gmv"]), _percent(row["gmv_7d_change"]), row["asp_status"],
            )
            for row in dfc["mtd_by_sku"]
        ),
    )
    return f"""# STORM Weekly Sales Review

Snapshot: `{manifest['snapshot_id']}`  
Source SHA-256: `{manifest['source_sha256']}`

## 1. Data Freshness

- Common Sales — Data Through: **{freshness['common_sales_data_through']}**
- THD DFC Sell-out — Data Through: **{freshness['thd_dfc_data_through']}**
- Common Sales scope: 2026-08-01 through {freshness['common_sales_data_through']}

## 2. Executive Sales Snapshot

- Actual Sales: **{_currency(total['actual_sales'])}**
- Units: **{_number(total['units'])}**
- Distinct Orders: **{_number(total['orders'])}**
- ASP: **{_currency(total['asp'])}**
- BP: **N/A — exact-period compatible BP is not available**
- Data Through: **{freshness['common_sales_data_through']}**

{platform_table}

## 3. Platform / Channel Performance

The table above is ranked by current sell-in contribution. BP gap and attainment are intentionally `N/A` because the approved BP is full-month August while Actual is only through {freshness['common_sales_data_through']}.

## 4. Brand Performance

{brand_table}

Data Through: **{freshness['common_sales_data_through']}**

## 5. Power Source Performance

{power_table}

Data Through: **{freshness['common_sales_data_through']}**

## 6. SKU Performance

### Top Sales Contributors

{sku_table}

### Lowest Sales Contributors

{lowest_sku_table}

These are the lowest current sales contributions, not a performance-failure judgment.

Top BP Detractors / Overperformers: **N/A — `BP_NOT_AVAILABLE` for the exact Actual period.**  
BP match coverage: **{review['bp_match_coverage']['matched_group_count']} matched SKU / {review['bp_match_coverage']['unmatched_group_count']} unmatched SKU; {_percent(review['bp_match_coverage']['matched_actual_sales_pct'])} matched sales / {_percent(review['bp_match_coverage']['unmatched_actual_sales_pct'])} unmatched sales.**  
Data Through: **{freshness['common_sales_data_through']}**

## 7. THD DFC Sell-out

- MTD Units: **{_number(dfc['mtd_total']['units'])}**
- MTD GMV: **{_currency(dfc['mtd_total']['gmv'])}**
- MTD period: **{dfc['mtd_period_start']} through {dfc['data_through']}**
- Recent 7D window: **{dfc['recent_window']['recent_start']} through {dfc['recent_window']['recent_end']}**
- Previous 7D window: **{dfc['recent_window']['previous_start']} through {dfc['recent_window']['previous_end']}**

{dfc_table}

THD DFC remains an independent consumer sell-out domain and is not included in Common Sales sell-in revenue.

## 8. Weekly Review Takeaways

{takeaway_lines}

## 9. Data Quality / Caveats

{warning_lines}

## Reconciliation Status

- Common Sales raw → normalized: **{review['reconciliation']['common_sales']['status']}**
- THD DFC raw → normalized: **{review['reconciliation']['thd_dfc']['status']}**
- Sales hierarchy roll-up: **{review['reconciliation']['hierarchy_rollup']['status']}**
"""


def generate_phase2(
    workbook_path: Path,
    project_root: Path | None = None,
    *,
    snapshot_date: date | None = None,
    snapshot_root: Path | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    data = build_phase2_data(workbook_path, project_root, snapshot_date)
    review = build_review(data)
    reconciliation_status = {
        name: value["status"] for name, value in review["reconciliation"].items()
    }
    manifest = write_snapshot(
        data,
        snapshot_root or project_root / "data" / "snapshots",
        manifest_extra={"reconciliation_status": reconciliation_status},
    )
    payload = {"snapshot": manifest, **review}
    report_dir = (report_dir or project_root / "reports" / "phase2").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "weekly_sales_review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (report_dir / "weekly_sales_review.md").write_text(
        render_markdown(review, manifest), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=Path("STORM V2 RAW DATA.xlsx"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot-date", type=date.fromisoformat)
    args = parser.parse_args()
    payload = generate_phase2(
        args.workbook,
        args.project_root,
        snapshot_date=args.snapshot_date,
    )
    print(
        json.dumps(
            {
                "status": "STORM_V2_PHASE_2_SALES_ENGINE_READY",
                "snapshot_id": payload["snapshot"]["snapshot_id"],
                "reconciliation": {
                    name: value["status"] for name, value in payload["reconciliation"].items()
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
