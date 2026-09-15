"""Snapshot-to-snapshot comparison; it never redefines base business metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb


def _published_manifests(project_root: Path) -> list[dict[str, Any]]:
    catalog = project_root / "data" / "storm.duckdb"
    statuses: dict[str, str] = {}
    if catalog.exists():
        connection = duckdb.connect(str(catalog), read_only=True)
        try:
            statuses = dict(connection.execute("SELECT snapshot_id, status FROM snapshot_registry").fetchall())
        finally:
            connection.close()
    manifests = []
    for path in (project_root / "data" / "snapshots").glob("*_r*/manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if statuses.get(manifest["snapshot_id"], manifest["status"]) == "PUBLISHED":
            manifests.append(manifest)
    return sorted(manifests, key=lambda row: (row["snapshot_date"], row["revision"]))


def previous_valid_snapshot(project_root: Path, *, exclude_week_key: str | None = None) -> dict[str, Any] | None:
    manifests = [
        manifest for manifest in _published_manifests(project_root)
        if manifest.get("week_key") != exclude_week_key
    ]
    return manifests[-1] if manifests else None


def compare_package_to_previous(project_root: Path, package: dict[str, Any], *, week_key: str | None = None) -> dict[str, Any]:
    previous = previous_valid_snapshot(project_root, exclude_week_key=week_key)
    if previous is None:
        return {"availability": "N/A_NO_PREVIOUS_VALID_SNAPSHOT"}
    current = package["executive"]
    prior = previous["reconciliation"]
    return {
        "availability": "AVAILABLE",
        "previous_snapshot_id": previous["snapshot_id"],
        "actual_delta": current["actual_sales"] - prior["actual_sales"],
        "gap_delta": current["sales_gap"] - prior["sales_gap"],
        "attainment_delta_pp": (current["attainment"] - prior["attainment"]) * 100,
        "cm_pct_delta_pp": None,
    }
