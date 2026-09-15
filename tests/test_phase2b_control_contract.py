from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
RULES = ROOT / "config" / "business_health_rules_v1_proposal.yaml"
REPORT = ROOT / "docs" / "phase2b_cockpit_calibration.md"


def test_rules_v1_is_bounded_and_inactive() -> None:
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    assert rules["status"] == "PROPOSAL_ONLY_PENDING_APPROVAL"
    assert rules["active"] is False
    assert rules["external_write_allowed"] is False
    assert rules["current_color_assignment_allowed"] is False
    assert rules["outputs"] == ["GREEN", "YELLOW", "RED", "UNKNOWN"]
    assert set(rules["domain_rules"]) == {
        "sales_health", "cm_health", "advertising_health", "inventory_health"
    }
    for rule in rules["domain_rules"].values():
        assert rule["threshold_source"].startswith("PENDING") or "require" in rule["threshold_source"]
        assert rule["unavailable_behavior"] == "UNKNOWN"


def test_overall_health_separates_business_from_data_confidence() -> None:
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    overall = rules["overall_health"]
    assert overall["method"] == "precedence_and_eligibility_not_average"
    assert overall["data_confidence"]["states"] == ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    assert any("unavailable data never becomes GREEN" in item for item in overall["business_health"])


def test_phase2b_report_records_required_semantic_conclusions_and_stop() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "SEMANTICALLY_VALID" in text
    assert "358.79 Auth Sales - 1,053.00 Refund sales = -694.21" in text
    assert "control_week = 2026-W33" in text
    assert "-78.8245916%" in text
    assert "two fields" in text
    assert "PHASE_2B_REVIEW_READY — RULE_AND_SCHEMA_APPROVAL_REQUIRED" in text
