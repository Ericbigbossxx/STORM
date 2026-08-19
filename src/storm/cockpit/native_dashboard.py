"""Phase 2F-R Feishu-native dashboard data mappings.

The accepted STORM artifacts remain the calculation authority.  This module
only maps those reviewed values into dashboard-compatible Feishu fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def _epoch_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def build_business_health_dashboard_fields(
    snapshot: Mapping[str, Any],
    phase2f: Mapping[str, Any],
) -> dict[str, float | int]:
    """Map accepted platform facts and derived metrics to live dashboard fields."""

    facts = snapshot["facts"]
    derived = snapshot["derived_control_metrics"]
    platform = phase2f["cockpit"]["platform"]
    weekly = derived["weekly_sales_change"]["value"]
    if weekly.get("availability") != "AVAILABLE":
        raise ValueError("WEEKLY_OPERATING_METRIC_NOT_AVAILABLE")
    if platform["control_week"] != snapshot["control_week"]:
        raise ValueError("CONTROL_WEEK_MISMATCH")

    return {
        "Actual Sales": facts["actual_sales"]["value"],
        "BP Sales": facts["bp_sales"]["value"],
        "Sales Gap": platform["sales_gap"],
        "Sales Attainment": derived["sales_attainment_pct"]["value"],
        "Weekly Operating Sales": weekly["current_value"],
        "Weekly Sales Change $": weekly["absolute_change"],
        "Weekly Sales Change %": weekly["percent_change"],
        "Actual CM": facts["actual_cm"]["value"],
        "BP CM": facts["bp_cm"]["value"],
        "CM Gap": facts["actual_cm"]["value"] - facts["bp_cm"]["value"],
        "CM Attainment": derived["cm_attainment_pct"]["value"],
        "CM %": derived["actual_cm_pct"]["value"],
        "Ad Spend": facts["ad_spend"]["value"],
        "Attributed Sales": facts["attributed_ad_sales"]["value"],
        "ROAS": facts["roas"]["value"],
        "Available Units": facts["inventory_units"]["value"],
        "OOS SKU Count": facts["inventory_condition"]["value"]["Out of Stock"],
        "Sales Data Through": _epoch_ms(facts["actual_sales"]["data_through_date"]),
        "CM Data Through": _epoch_ms(facts["actual_cm"]["data_through_date"]),
        "Ads Data Through": _epoch_ms(facts["ad_spend"]["data_through_date"]),
        "Inventory Data Through": _epoch_ms(facts["inventory_units"]["data_through_date"]),
    }


def build_core_dashboard_updates(
    phase2e: Mapping[str, Any],
    phase2f: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build updates for the accepted 14 records without inventing null values."""

    facts = {str(row["sku"]): row for row in phase2e["eligible_sku_facts"]}
    managed = list(phase2f["selection"]["managed_skus"])
    updates: list[dict[str, Any]] = []
    for sku in managed:
        fact = facts[sku]
        fields: dict[str, float] = {}
        if fact["target_delta"] is not None:
            fields["Sales Gap"] = fact["target_delta"]
        if fact["sales"] is not None and fact["target"] not in (None, 0.0):
            fields["Sales Attainment"] = fact["sales"] / fact["target"]
        if fact["ad_sales"] is not None:
            fields["Attributed Sales"] = fact["ad_sales"]
        updates.append(
            {
                "identity": f"SKU-{phase2f['cockpit']['platform']['control_week'].replace('-', '')}-US-WMT-{sku}",
                "sku": sku,
                "fields": fields,
            }
        )
    return updates

