"""Materialize an immutable STORM Phase 6 snapshot from the frozen Phase 5R package.

This script does not calculate Sales, BP, Gap, Attainment, CM, or SKU BP.  It only
copies the authoritative Phase 5R presentation datasets into local Parquet/DuckDB
storage together with an auditable manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _write_parquet(connection: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]], output: Path) -> None:
    staging = output.with_suffix(".json")
    staging.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    connection.execute("CREATE OR REPLACE TABLE stage AS SELECT * FROM read_json_auto(?)", [str(staging)])
    connection.execute(f"COPY stage TO '{output.as_posix()}' (FORMAT PARQUET)")
    connection.execute("DROP TABLE stage")
    staging.unlink()


def _source_records(
    project_root: Path,
    package: dict[str, Any],
    archive_dir: Path,
    package_path: Path,
    source_paths: list[Path] | None = None,
) -> list[dict[str, str]]:
    frozen_snapshot_dir = project_root / "data" / "snapshots" / package["source"]["actual_snapshot_id"]
    frozen_snapshot_manifest = json.loads((frozen_snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    if frozen_snapshot_manifest["source_sha256"] != package["source"]["actual_source_sha256"]:
        raise ValueError("Frozen normalized snapshot does not match the Phase 5R source hash")
    candidates = [
        (package_path, "phase6r_engine_package"),
        (frozen_snapshot_dir / "manifest.json", "frozen_normalized_snapshot_manifest"),
        (frozen_snapshot_dir / "canonical_records.csv", "frozen_normalized_actual_and_dfc"),
        (Path(package["source"]["bp"]["path"]), "bp_and_cm"),
    ]
    candidates.extend((path.resolve(), f"weekly_source_{index}") for index, path in enumerate(source_paths or [], 1))
    records: list[dict[str, str]] = []
    for source, source_type in candidates:
        if not source.exists():
            raise FileNotFoundError(f"Required frozen source is missing: {source}")
        source_hash = sha256(source)
        target = archive_dir / f"{source_hash[:12]}_{source.name}"
        if not target.exists():
            shutil.copy2(source, target)
        if sha256(target) != source_hash:
            raise ValueError(f"Source archive hash mismatch: {source.name}")
        records.append({
            "source_type": source_type,
            "original_filename": source.name,
            "sha256": source_hash,
            "archive_path": str(target),
        })
    return records


def _snapshot_rows(package: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "sku_metrics": package["sku_actual_vs_bp"]["rows"],
        "channel_health": package["channel_health"],
        "driver_metrics": package["business_drivers"],
        "thd_dfc_daily": package["thd_dfc"]["daily_trend"],
        "thd_dfc_sku": package["thd_dfc"]["mtd_by_sku"],
        "findings": package["key_findings"],
        "scope_exclusions": package["sku_bp"].get("excluded_source_rows", []),
        "ytd_metrics": [package.get("ytd", {})],
    }


def register_snapshot(project_root: Path, manifest: dict[str, Any], manifest_path: Path) -> None:
    catalog = project_root / "data" / "storm.duckdb"
    catalog_connection = duckdb.connect(str(catalog))
    try:
        catalog_connection.execute("""CREATE TABLE IF NOT EXISTS snapshot_registry (
            snapshot_id VARCHAR PRIMARY KEY, week_key VARCHAR, snapshot_date DATE,
            revision INTEGER, status VARCHAR, manifest_path VARCHAR, created_at TIMESTAMPTZ
        )""")
        catalog_connection.execute(
            "INSERT OR IGNORE INTO snapshot_registry VALUES (?, ?, ?, ?, ?, ?, ?)",
            [manifest["snapshot_id"], manifest["week_key"], manifest["snapshot_date"], manifest["revision"], manifest["status"], str(manifest_path), manifest["created_at"]],
        )
    finally:
        catalog_connection.close()


def mark_superseded(project_root: Path, snapshot_id: str, status: str) -> None:
    """Record lifecycle state in the mutable catalog without changing the snapshot."""
    catalog = project_root / "data" / "storm.duckdb"
    connection = duckdb.connect(str(catalog))
    try:
        connection.execute(
            "UPDATE snapshot_registry SET status = ? WHERE snapshot_id = ?",
            [status, snapshot_id],
        )
        if connection.execute(
            "SELECT COUNT(*) FROM snapshot_registry WHERE snapshot_id = ?", [snapshot_id]
        ).fetchone()[0] != 1:
            raise ValueError(f"Cannot supersede unregistered snapshot: {snapshot_id}")
    finally:
        connection.close()


def build_snapshot(
    project_root: Path,
    snapshot_date: str,
    revision: int | None = None,
    package_path: Path | None = None,
    supersedes: str | None = None,
    source_paths: list[Path] | None = None,
    manifest_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    package_path = (package_path or project_root / "reports" / "phase5r" / "phase5r_package.json").resolve()
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if package["status"] != "STORM_V2_PHASE_5R_WEEKLY_COCKPIT_READY":
        raise ValueError("Phase 5R package is not frozen-ready")
    if package["reconciliation"]["status"] != "PASS":
        raise ValueError("Phase 5R reconciliation is not PASS")

    week_key = datetime.fromisoformat(snapshot_date).isocalendar()
    week_label = f"{week_key.year}-W{week_key.week:02d}"
    snapshots_root = project_root / "data" / "snapshots"
    revisions = [path for path in snapshots_root.glob(f"{snapshot_date}_r*") if path.is_dir()]
    next_revision = max((int(path.name.rsplit("r", 1)[1]) for path in revisions), default=0) + 1
    revision = revision or next_revision
    snapshot_id = f"{snapshot_date}_r{revision}"
    snapshot_dir = snapshots_root / snapshot_id
    if snapshot_dir.exists():
        raise FileExistsError(f"Snapshot already exists and is immutable: {snapshot_id}")

    snapshot_dir.mkdir(parents=True)
    archive_dir = project_root / "data" / "source_archive" / snapshot_id
    archive_dir.mkdir(parents=True)
    source_records = _source_records(project_root, package, archive_dir, package_path, source_paths)
    rows = _snapshot_rows(package)
    database = snapshot_dir / "storm.duckdb"
    connection = duckdb.connect(str(database))
    try:
        for table_name, table_rows in rows.items():
            _write_parquet(connection, table_rows, snapshot_dir / f"{table_name}.parquet")
    finally:
        connection.close()

    manifest = {
        "snapshot_id": snapshot_id,
        "week_key": week_label,
        "snapshot_date": snapshot_date,
        "revision": revision,
        "created_at": datetime.now(UTC).isoformat(),
        "sales_cutoff": max(
            (row.get("period_end") for row in package["sku_actual_vs_bp"]["rows"] if row.get("period_end")),
            default=snapshot_date,
        ),
        "dfc_cutoff": package["thd_dfc"]["data_through"],
        "cm_period": f"{package['period']['month_label']} MTD",
        "operating_cost_period": f"{package['period']['month_label']} MTD",
        "source_hashes": {record["source_type"]: record["sha256"] for record in source_records},
        "authoritative_actual_source_sha256": package["source"]["actual_source_sha256"],
        "actual_source_provenance": "FROZEN_NORMALIZED_PHASE2_SNAPSHOT",
        "source_exception": "Current STORM V2 RAW DATA.xlsx hash differs from the frozen Phase 5R source hash; this snapshot consumes the matching frozen normalized output and does not claim the current workbook as its source.",
        "source_archive": source_records,
        "engine_version": "phase6r_bp_scope_reconciliation",
        "status": "PUBLISHED",
        "supersedes": supersedes,
        "supersession_reasons": (
            ["BP_AGGREGATION_RECONCILIATION_FIX", "PERCENTAGE_DISPLAY_FIX", "EXECUTIVE_FILTER_FIX"]
            if supersedes else []
        ),
        "reconciliation": {
            "actual_sales": package["executive"]["actual_sales"],
            "bp_sales": package["executive"]["bp_sales"],
            "sales_gap": package["executive"]["sales_gap"],
            "attainment": package["executive"]["attainment"],
            "sku_bp_control": package["reconciliation"]["walmart_badger_gas_control"],
            "bp_hierarchy": package["reconciliation"],
            "status": package["reconciliation"]["status"],
        },
        "datasets": {name: f"{name}.parquet" for name in rows},
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    register_snapshot(project_root, manifest, snapshot_dir / "manifest.json")
    published = project_root / "data" / "published"
    published.mkdir(parents=True, exist_ok=True)
    (published / f"{snapshot_id}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot-date", default="2026-08-14")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--package-path", type=Path)
    parser.add_argument("--supersedes")
    parser.add_argument("--register-existing", type=Path)
    args = parser.parse_args()
    if args.register_existing:
        manifest_path = args.register_existing.resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        register_snapshot(args.project_root.resolve(), manifest, manifest_path)
        print(json.dumps({"registered": manifest["snapshot_id"]}, indent=2))
        return 0
    manifest = build_snapshot(
        args.project_root,
        args.snapshot_date,
        args.revision,
        args.package_path,
        args.supersedes,
    )
    if args.supersedes:
        mark_superseded(
            args.project_root.resolve(),
            args.supersedes,
            "SUPERSEDED_DATA_RECONCILIATION_ERROR",
        )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
