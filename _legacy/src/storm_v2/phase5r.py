"""Build the Phase 5R data package without mutating approved sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from .sku_bp import (
    PHASE5R_DATA_STATUS,
    PHASE5R_READY_STATUS,
    aggregate_bp,
    extract_sku_bp,
    gap_rankings,
    join_actual_bp,
    load_actual_sku_sales,
    reconcile_bp,
)


REPORT_HEADINGS = (
    "STATUS",
    "SKU BP REPAIR",
    "BP RECONCILIATION",
    "SKU ACTUAL VS BP RESULT",
    "TOP SKU DETRACTORS",
    "TOP SKU OVERPERFORMERS",
    "EXECUTIVE VIEW",
    "CHANNEL HEALTH VIEW",
    "BUSINESS DRIVER VIEW",
    "THD DFC VIEW",
    "KEY FINDINGS VIEW",
    "DATA FRESHNESS",
    "VISUAL CHANGES",
    "3-MINUTE WEEKLY REVIEW TEST",
    "TESTS",
    "SOURCE MUTATION",
    "FILES MODIFIED",
    "FEISHU COMPONENTS CREATED / REMOVED / REPLACED",
    "KNOWN LIMITATIONS",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def _sum_present(rows: Iterable[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return sum(values) if values else None


def _attainment(actual: float, bp: float | None) -> float | None:
    return actual / bp if bp is not None and bp > 0 else None


def _rollup(
    rows: Iterable[dict[str, Any]], group_by: Sequence[str]
) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[tuple(row[field] for field in group_by)].append(row)
    output = []
    for key, members in sorted(buckets.items()):
        actual = sum(float(row["actual_sales"]) for row in members)
        bp = _sum_present(members, "bp_sales")
        item = {field: value for field, value in zip(group_by, key)}
        item.update(
            {
                "actual_sales": actual,
                "bp_sales": bp,
                "sales_gap": actual - bp if bp is not None else None,
                "attainment": _attainment(actual, bp),
                "bp_status": "AVAILABLE" if bp is not None else "BP_NOT_AVAILABLE",
            }
        )
        output.append(item)
    return output


def _channel_health(
    joined: list[dict[str, Any]], phase4: dict[str, Any]
) -> list[dict[str, Any]]:
    cm_index = {
        (row["platform"], row["channel"]): row
        for row in phase4["channel_performance"]
    }
    output = []
    for row in _rollup(joined, ("platform", "channel")):
        cm = cm_index[(row["platform"], row["channel"])]
        row.update(
            {
                "actual_cm": cm.get("actual_cm"),
                "bp_cm": cm.get("bp_cm"),
                "cm_gap": cm.get("cm_gap"),
                "tacos": cm.get("tacos"),
                "return_warranty_cost_rate": cm.get("return_warranty_cost_rate"),
                "known_operating_cost_burden_rate": cm.get(
                    "known_operating_cost_burden_rate"
                ),
                "cm_status": cm.get("cm_status"),
                "operating_status": cm.get("operating_status"),
            }
        )
        output.append(row)
    return output


def _drivers(joined: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _rollup(
        joined, ("platform", "channel", "brand", "power_source")
    )
    for row in rows:
        row.update(
            {
                "actual_cm": None,
                "cm_status": "NOT_AVAILABLE_NO_LOWER_LEVEL_ALLOCATION",
            }
        )
    return sorted(rows, key=lambda row: row["sales_gap"] if row["sales_gap"] is not None else 0)


def _findings(
    channel_rows: list[dict[str, Any]], driver_rows: list[dict[str, Any]]
) -> list[dict[str, str]]:
    risk = min(channel_rows, key=lambda row: row["sales_gap"])
    weak_cm = min(channel_rows, key=lambda row: row["actual_cm"])
    burden = max(
        channel_rows, key=lambda row: row["known_operating_cost_burden_rate"]
    )
    strength = max(channel_rows, key=lambda row: row["actual_sales"])
    driver = min(
        (row for row in driver_rows if row["sales_gap"] is not None),
        key=lambda row: row["sales_gap"],
    )
    return [
        {
            "type": "MAIN RISK",
            "text": (
                f"{risk['platform']} / {risk['channel']} has the largest Sales Gap "
                f"at ${risk['sales_gap']:,.0f}; attainment is {risk['attainment']:.1%}."
            ),
        },
        {
            "type": "WHY",
            "text": (
                f"{driver['platform']} / {driver['channel']} × {driver['brand']} × "
                f"{driver['power_source']} is the largest driver at "
                f"${driver['sales_gap']:,.0f} Gap."
            ),
        },
        {
            "type": "WATCH",
            "text": (
                f"{weak_cm['platform']} / {weak_cm['channel']} has the weakest CM "
                f"at {weak_cm['actual_cm']:.2%}; {burden['platform']} / "
                f"{burden['channel']} has the highest known burden at "
                f"{burden['known_operating_cost_burden_rate']:.2%}."
            ),
        },
        {
            "type": "STRENGTH",
            "text": (
                f"{strength['platform']} / {strength['channel']} leads Actual Sales "
                f"at ${strength['actual_sales']:,.0f} with {strength['actual_cm']:.2%} CM."
            ),
        },
    ]


def build_phase5r_package(
    *,
    bp_workbook: Path,
    actual_snapshot_csv: Path,
    snapshot_manifest: Path,
    phase4_json: Path,
    year: int = 2026,
    month: int = 8,
    visual_ready: bool = False,
    ytd_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bp_hash_before = _sha256(bp_workbook)
    actual_snapshot_hash_before = _sha256(actual_snapshot_csv)
    extraction = extract_sku_bp(bp_workbook, year=year, month=month)
    reconciliation = reconcile_bp(extraction)
    if reconciliation["status"] not in ("PASS", "SKIP_NO_BASELINE"):
        raise ValueError("BP reconciliation failed; Feishu writes are forbidden")
    actual_rows = load_actual_sku_sales(actual_snapshot_csv)
    joined = join_actual_bp(actual_rows, extraction["rows"])
    rankings = gap_rankings(joined, limit=8)
    phase4 = _load_json(phase4_json)
    manifest = _load_json(snapshot_manifest)
    channels = _channel_health(joined, phase4)
    drivers = _drivers(joined)
    actual_total = sum(row["actual_sales"] for row in joined)
    bp_total = _sum_present(joined, "bp_sales")
    source_mutation = {
        "bp_workbook_before": bp_hash_before,
        "bp_workbook_after": _sha256(bp_workbook),
        "actual_snapshot_before": actual_snapshot_hash_before,
        "actual_snapshot_after": _sha256(actual_snapshot_csv),
    }
    source_mutation["status"] = (
        "NONE"
        if source_mutation["bp_workbook_before"]
        == source_mutation["bp_workbook_after"]
        and source_mutation["actual_snapshot_before"]
        == source_mutation["actual_snapshot_after"]
        else "DETECTED"
    )
    if source_mutation["status"] != "NONE":
        raise ValueError("approved source changed during Phase 5R build")
    return {
        "status": PHASE5R_READY_STATUS if visual_ready else PHASE5R_DATA_STATUS,
        "period": extraction["period"],
        "source": {
            "bp": extraction["source"],
            "actual_snapshot_id": manifest["snapshot_id"],
            "actual_source_sha256": manifest["source_sha256"],
        },
        "source_mutation": source_mutation,
        "sku_bp": {
            "availability": "AVAILABLE",
            "row_count": len(extraction["rows"]),
            "source_row_count": extraction["source_row_count"],
            "promotion_header_alias_used": extraction["source"]["promotion_header"],
            "rows": extraction["rows"],
            "scope_definition": extraction["scope_definition"],
            "excluded_source_rows": extraction["excluded_source_rows"],
            "excluded_bp_sales": extraction["excluded_bp_sales"],
        },
        "reconciliation": reconciliation,
        "sku_actual_vs_bp": {
            "sku_bp": "AVAILABLE",
            "sku_gap": "AVAILABLE",
            "sku_attainment": "AVAILABLE",
            "row_count": len(joined),
            "matched_count": sum(row["actual_present"] and row["bp_present"] for row in joined),
            "bp_only_count": sum((not row["actual_present"]) and row["bp_present"] for row in joined),
            "actual_only_count": sum(row["actual_present"] and (not row["bp_present"]) for row in joined),
            "rows": joined,
        },
        "executive": {
            "actual_sales": actual_total,
            "bp_sales": bp_total,
            "sales_gap": actual_total - bp_total if bp_total is not None else None,
            "attainment": _attainment(actual_total, bp_total),
            "actual_cm": None,
            "cm_gap": None,
            "cm_status": "NOT_AVAILABLE_NO_COMPATIBLE_OVERALL_SOURCE",
        },
        "channel_health": channels,
        "business_drivers": drivers,
        "top_sku_detractors": rankings["top_detractors"],
        "top_sku_overperformers": rankings["top_overperformers"],
        "unplanned_sales": rankings["unplanned_sales"],
        "key_findings": _findings(channels, drivers),
        "thd_dfc": phase4["thd_dfc_sellout"],
        "data_freshness": (
            f"Sales through {phase4['freshness']['common_sales']['data_through']} | "
            f"DFC through {phase4['freshness']['thd_dfc_sellout']['data_through']} | "
            f"CM {phase4['freshness']['cm_business_performance']['period_label']} | "
            f"Operating Cost {phase4['freshness'].get('operating_efficiency', {}).get('period_label', 'N/A')} | "
            f"CM exact cutoff unknown"
        ),
        "ytd": ytd_metrics or {"availability": {"status": "N/A_NOT_EXTRACTED"}},
        "visual_acceptance": {
            "status": "PASS" if visual_ready else "PENDING",
            "three_minute_opening_test": "PASS" if visual_ready else "PENDING",
        },
    }


def _sku_line(row: dict[str, Any]) -> str:
    attainment = "N/A" if row["attainment"] is None else f"{row['attainment']:.1%}"
    return (
        f"- {row['platform']} / {row['channel']} | {row['sku']} | "
        f"{row['brand']} / {row['power_source']} | Actual ${row['actual_sales']:,.2f} | "
        f"BP ${row['bp_sales']:,.2f} | Gap ${row['sales_gap']:,.2f} | {attainment}"
    )


def render_completion_report(package: dict[str, Any]) -> str:
    control = package["reconciliation"]["walmart_badger_gas_control"]
    detractors = "\n".join(_sku_line(row) for row in package["top_sku_detractors"])
    overperformers = "\n".join(_sku_line(row) for row in package["top_sku_overperformers"])
    sections = {
        "STATUS": f"`{package['status']}`",
        "SKU BP REPAIR": (
            "SKU BP: AVAILABLE\n\nSKU Gap: AVAILABLE\n\nSKU Attainment: AVAILABLE\n\n"
            f"Promotion header alias accepted: `{package['sku_bp']['promotion_header_alias_used']}`."
        ),
        "BP RECONCILIATION": (
            f"Walmart Aug Badger Gas BP:\n\nExpected = {control['expected']:.2f}\n\n"
            f"Actual = {control['actual']:.2f}\n\nReconciliation = {control['status']}\n\n"
            f"Three-level reconciliation = {package['reconciliation']['status']}"
        ),
        "SKU ACTUAL VS BP RESULT": (
            f"{package['sku_actual_vs_bp']['row_count']} Channel × SKU rows; "
            f"matched {package['sku_actual_vs_bp']['matched_count']}, "
            f"BP-only {package['sku_actual_vs_bp']['bp_only_count']}, "
            f"Actual-only {package['sku_actual_vs_bp']['actual_only_count']}."
        ),
        "TOP SKU DETRACTORS": detractors,
        "TOP SKU OVERPERFORMERS": overperformers,
        "EXECUTIVE VIEW": "Pending/recorded in live Feishu cockpit acceptance evidence.",
        "CHANNEL HEALTH VIEW": "Pending/recorded in live Feishu cockpit acceptance evidence.",
        "BUSINESS DRIVER VIEW": "Pending/recorded in live Feishu cockpit acceptance evidence.",
        "THD DFC VIEW": "Phase 4 DFC data reused unchanged and moved below the executive section.",
        "KEY FINDINGS VIEW": "Four current-data findings generated dynamically.",
        "DATA FRESHNESS": package["data_freshness"],
        "VISUAL CHANGES": "Pending/recorded after live Dashboard replacement.",
        "3-MINUTE WEEKLY REVIEW TEST": package["visual_acceptance"]["three_minute_opening_test"],
        "TESTS": "Pending final targeted and full regression evidence.",
        "SOURCE MUTATION": "Workbook mutation = NONE",
        "FILES MODIFIED": "Pending final file inventory.",
        "FEISHU COMPONENTS CREATED / REMOVED / REPLACED": "Pending live reconciliation.",
        "KNOWN LIMITATIONS": (
            "Overall Actual CM and CM Gap remain N/A because no compatible overall source exists; "
            "driver-level CM is not allocated."
        ),
    }
    return "\n\n".join(f"## {heading}\n\n{sections[heading]}" for heading in REPORT_HEADINGS) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bp-workbook", type=Path, required=True)
    parser.add_argument("--actual-snapshot", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--phase4-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--visual-ready", action="store_true")
    args = parser.parse_args()
    package = build_phase5r_package(
        bp_workbook=args.bp_workbook,
        actual_snapshot_csv=args.actual_snapshot,
        snapshot_manifest=args.snapshot_manifest,
        phase4_json=args.phase4_json,
        visual_ready=args.visual_ready,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "phase5r_package.json").open("w", encoding="utf-8") as handle:
        json.dump(package, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    (args.output_dir / "phase5r_completion_report.md").write_text(
        render_completion_report(package), encoding="utf-8"
    )
    print(json.dumps({"status": package["status"], "output_dir": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
