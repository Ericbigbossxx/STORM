from __future__ import annotations

import json
from pathlib import Path

from storm.cockpit.weekly_cockpit import build_dashboard_artifact, build_phase2f_package


ROOT = Path(__file__).parents[1]


def _package() -> dict:
    phase2e = json.loads(
        (ROOT / "data/cockpit/phase2e/walmart_weekly_driver_package.json").read_text(
            encoding="utf-8"
        )
    )
    health = json.loads(
        (ROOT / "data/cockpit/phase2c/walmart_business_health_snapshot_v3.json").read_text(
            encoding="utf-8"
        )
    )
    return build_phase2f_package(
        phase2e,
        health,
        ROOT / "config/feishu_schema.yaml",
        live_record_count=0,
    )


def test_phase2f_managed_and_cockpit_scope_is_deterministic_and_practical() -> None:
    package = _package()
    selection = package["selection"]
    assert selection["all_fact_count"] == 55
    assert selection["strategic_eligible_count"] == 43
    assert selection["managed_skus"] == [
        "ORIONX7",
        "SKRMS4",
        "SKRMV3",
        "SKRMX3PLUS",
        "SKRMX5",
        "WB20V16LM",
        "WB20VTAB",
        "WB20VTRSBL",
        "WB26MTSE",
        "WB40V18PLM",
        "WB40VTBCC",
        "WB40VTRED",
        "WB53CULT",
        "WBPMT26P",
    ]
    assert selection["cockpit_driver_skus"] == [
        "SKRMX3PLUS",
        "WB20V16LM",
        "WB40V18PLM",
        "SKRMV3",
        "WB40VTBCC",
        "WB40VTRED",
        "WB20VTRSBL",
        "WB53CULT",
        "WB26MTSE",
        "WBPMT26P",
    ]
    assert all(sku in selection["managed_skus"] for sku in selection["cockpit_driver_skus"])
    assert "SK-V-MAGSTRIP" not in selection["managed_skus"]
    assert "WB26BCI" not in selection["managed_skus"]


def test_phase2f_preserves_authoritative_roles_and_builds_only_managed_candidates() -> None:
    package = _package()
    candidates = package["feishu_candidate_set"]
    assert candidates["candidate_count"] == 14
    assert candidates["expected_behavior"] == "CREATE"
    by_sku = {row["sku"]: row for row in candidates["candidates"]}
    assert by_sku["ORIONX7"]["fields"]["SKU Role"] == "CORE"
    assert by_sku["WB20V16LM"]["fields"]["SKU Role"] == "GROWTH"
    assert by_sku["WB40VTRED"]["fields"]["SKU Role"] == "PROFIT"
    assert all(row["fields"]["Status"] == "UNKNOWN" for row in by_sku.values())
    assert all(row["fields"]["Human Reviewed"] is False for row in by_sku.values())
    assert package["governance"]["sku_records_written"] == 0
    assert package["governance"]["signal_records_created"] == 0
    assert package["governance"]["action_records_created"] == 0


def test_phase2f_cockpit_artifact_is_business_first_and_uses_valid_weekly_periods() -> None:
    package = _package()
    artifact = build_dashboard_artifact(package)
    assert artifact["surface"] == "report"
    assert artifact["manifest"]["surface"] == "report"
    assert len(artifact["manifest"]["cards"]) == 13
    assert artifact["manifest"]["blocks"][0]["id"] == "status"
    trend = artifact["snapshot"]["datasets"]["weekly_trend"]
    assert [row["period_type"] for row in trend] == ["WEEKLY_OPERATING", "WEEKLY_OPERATING"]
    assert [row["weekly_sales"] for row in trend] == [2115.52, 447.97]
    assert artifact["manifest"]["charts"][0]["type"] == "bar"
    visible_text = json.dumps(artifact["manifest"]["blocks"], ensure_ascii=False)
    assert "batch" not in visible_text.lower()
    assert "field_id" not in visible_text.lower()
    assert "table_id" not in visible_text.lower()
    assert package["cockpit"]["platform"]["overall_health"] == "RED"
    assert package["cockpit"]["platform"]["data_confidence"] == "MEDIUM"
