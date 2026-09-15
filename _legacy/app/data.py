from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS_ROOT = PROJECT_ROOT / "data" / "snapshots"


def snapshot_options() -> list[dict]:
    statuses: dict[str, str] = {}
    catalog = PROJECT_ROOT / "data" / "storm.duckdb"
    if catalog.exists():
        connection = duckdb.connect(str(catalog), read_only=True)
        try:
            statuses = dict(connection.execute("SELECT snapshot_id, status FROM snapshot_registry").fetchall())
        finally:
            connection.close()
    options = []
    for manifest_path in SNAPSHOTS_ROOT.glob("*_r*/manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = statuses.get(manifest["snapshot_id"], manifest["status"])
        options.append(manifest)
    return sorted(options, key=lambda item: (item["snapshot_date"], item["revision"]), reverse=True)


@st.cache_data(show_spinner=False)
def load_snapshot(snapshot_id: str) -> dict:
    snapshot_dir = SNAPSHOTS_ROOT / snapshot_id
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    connection = duckdb.connect()
    try:
        datasets = {
            name: connection.execute("SELECT * FROM read_parquet(?)", [str(snapshot_dir / file_name)]).df()
            for name, file_name in manifest["datasets"].items()
        }
    finally:
        connection.close()
    return {"manifest": manifest, **datasets}


def apply_filters(frame: pd.DataFrame, filters: dict) -> pd.DataFrame:
    filtered = frame.copy()
    for column in ("platform", "channel", "brand", "power_source", "sku"):
        value = filters.get(column)
        if value and value != "All" and column in filtered.columns:
            filtered = filtered[filtered[column] == value]
    return filtered


def _ratio(actual: float, bp: float | None) -> float | None:
    return actual / bp if bp is not None and bp > 0 else None


def metric_context(data: dict, filters: dict, period: str) -> dict:
    """Compute filtered cockpit metrics from frozen engine rows, never UI formulas."""
    if period == "YTD":
        ytd = data["manifest"].get("ytd")
        if not ytd and "ytd_metrics" in data and not data["ytd_metrics"].empty:
            ytd = data["ytd_metrics"].iloc[0].to_dict()
        ytd = ytd or {}
        return {
            "period": "YTD",
            "period_source": ytd.get("source", "AUTHORITATIVE_CM_WORKBOOK"),
            "availability": "AVAILABLE" if ytd.get("actual_sales") is not None and ytd.get("bp_sales") is not None else "N/A_NO_COMPATIBLE_YTD_SALES_BP_EXTRACT",
            "sku_rows": data["sku_metrics"].iloc[0:0].copy(),
            "drivers": data["driver_metrics"].iloc[0:0].copy(),
            "channels": data["channel_health"].iloc[0:0].copy(),
            "actual_sales": ytd.get("actual_sales"), "bp_sales": ytd.get("bp_sales"), "sales_gap": ytd.get("sales_gap"),
            "attainment": ytd.get("attainment"), "actual_cm": ytd.get("actual_cm"), "bp_cm": ytd.get("bp_cm"),
            "cm_gap": ytd.get("cm_gap"), "wow": {},
        }
    sku_rows = apply_filters(data["sku_metrics"], filters)
    bp_values = sku_rows["bp_sales"].dropna()
    actual = float(sku_rows["actual_sales"].sum())
    bp = float(bp_values.sum()) if not bp_values.empty else None
    channel_filters = {key: filters.get(key) for key in ("platform", "channel")}
    channels = apply_filters(data["channel_health"], channel_filters)
    drivers = apply_filters(data["driver_metrics"], filters).copy()
    if not drivers.empty:
        drivers["gap_contribution"] = drivers["sales_gap"] / drivers["sales_gap"].sum() if drivers["sales_gap"].sum() else None
    cm = channels.iloc[0].to_dict() if len(channels) == 1 and all(
        not filters.get(key) or filters.get(key) == "All" for key in ("brand", "power_source", "sku")
    ) else {}
    return {
        "period": "MTD", "period_source": "FROZEN_ENGINE_AND_AUTHORITATIVE_CM_WORKBOOK",
        "availability": "AVAILABLE", "sku_rows": sku_rows, "drivers": drivers,
        "channels": channels, "actual_sales": actual, "bp_sales": bp,
        "sales_gap": actual - bp if bp is not None else None,
        "attainment": _ratio(actual, bp), "actual_cm": cm.get("actual_cm"),
        "bp_cm": cm.get("bp_cm"), "cm_gap": cm.get("cm_gap"),
        "wow": data["manifest"].get("wow", {}),
    }
