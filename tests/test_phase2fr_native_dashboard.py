import json
from pathlib import Path

import pytest
import yaml

from storm.cockpit.native_dashboard import (
    build_business_health_dashboard_fields,
    build_core_dashboard_updates,
)


ROOT = Path(__file__).parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_business_health_dashboard_payload_preserves_native_cutoffs() -> None:
    fields = build_business_health_dashboard_fields(
        _json("data/cockpit/phase2c/walmart_business_health_snapshot_v3.json"),
        _json("data/cockpit/phase2f/walmart_phase2f_control_package.json"),
    )
    assert fields["Actual Sales"] == -694.21
    assert fields["Sales Gap"] == pytest.approx(-208205.91)
    assert fields["CM Gap"] == pytest.approx(-18791.798611995155)
    assert fields["Weekly Operating Sales"] == 447.97
    assert fields["Weekly Sales Change $"] == -1667.55
    assert fields["Available Units"] == 884
    assert fields["OOS SKU Count"] == 22
    assert fields["Sales Data Through"] != fields["CM Data Through"]
    assert "Data As Of" not in fields


def test_core_dashboard_updates_are_bounded_and_preserve_nulls() -> None:
    phase2e = _json("data/cockpit/phase2e/walmart_weekly_driver_package.json")
    phase2f = _json("data/cockpit/phase2f/walmart_phase2f_control_package.json")
    updates = build_core_dashboard_updates(phase2e, phase2f)
    assert len(updates) == 14
    assert {row["sku"] for row in updates} == set(phase2f["selection"]["managed_skus"])
    assert all(set(row["fields"]) <= {"Sales Gap", "Sales Attainment", "Attributed Sales"} for row in updates)
    by_sku = {row["sku"]: row["fields"] for row in updates}
    assert by_sku["SKRMX3PLUS"]["Sales Gap"] == -43173.0
    assert by_sku["SKRMX3PLUS"]["Sales Attainment"] == -0.0
    assert "Sales Gap" not in by_sku["SKRMS4"]
    assert "Attributed Sales" not in by_sku["SKRMS4"]


def test_manual_dashboard_contract_is_exact_and_excludes_other_tables() -> None:
    contract = yaml.safe_load((ROOT / "config/dashboard_metric_contract_v1.yaml").read_text(encoding="utf-8"))
    components = contract["manual_dashboard"]["components"]
    assert contract["target_dashboard"] == "STORM Weekly Cockpit"
    assert {row["source"] for row in components} == {"01 Business Health", "02 Core SKU Performance"}
    assert len(contract["business_health_fields"]["currency"]) == 10
    assert contract["business_health_fields"]["omitted"]["YTD Availability/Status"]
    visible = json.dumps(contract, ensure_ascii=False)
    assert "03 Action" not in visible
    assert "04 Signal" not in visible

