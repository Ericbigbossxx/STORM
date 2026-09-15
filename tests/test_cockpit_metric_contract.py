from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "cockpit_metrics.yaml"
CONTRACT = ROOT / "docs" / "cockpit_metric_contract.md"
CHECKPOINT = ROOT / "docs" / "phase2a_walmart_cockpit_checkpoint.md"


def load_contract() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_cockpit_metric_contract_starts_from_management_use():
    contract = load_contract()
    assert contract["product_goal"] == "North America E-commerce Business Cockpit / Weekly Business Control System"
    assert contract["scope"]["first_vertical_slice"] == "WALMART_MP"
    assert contract["scope"]["feishu_schema_change_allowed"] is True
    assert contract["scope"]["phase2c_approved_feishu_schema_delta"] == [
        "CM Health", "Data Confidence"
    ]
    assert contract["scope"]["phase2c_live_record_write_allowed"] is False
    assert contract["scope"]["ui_build_in_phase_2a"] is False
    required = {
        "metric_name", "business_definition", "business_question", "source_authority", "grain",
        "period_type", "required_source", "calculation_rule", "null_behavior", "freshness_rule",
        "cockpit_destination", "can_trigger_signal", "can_validate_action", "classification",
    }
    metrics = contract["metrics"]
    assert metrics
    assert all(required <= set(metric) for metric in metrics)
    assert all(metric["business_question"].strip() for metric in metrics)
    assert len({metric["metric_name"] for metric in metrics}) == len(metrics)


def test_metric_and_freshness_vocabularies_are_bounded():
    contract = load_contract()
    allowed_classes = {"FOUNDATION", "OPERATING", "DERIVED_CONTROL", "DISPLAY_ONLY"}
    allowed_freshness = {"CURRENT", "LAGGING", "STALE", "SOURCE_NOT_AVAILABLE", "NOT_APPLICABLE"}
    assert set(contract["metric_classifications"]) == allowed_classes
    assert set(contract["freshness_states"]) == allowed_freshness
    assert {metric["classification"] for metric in contract["metrics"]} <= allowed_classes


def test_time_contract_preserves_native_cutoffs_and_forbids_false_alignment():
    time = load_contract()["time_semantics"]
    assert time["control_week_field"] == "control_week"
    assert time["feishu_control_week_field"] == "Week"
    assert "deprecated_generic_name" in time["week_role"]
    assert time["comparable_period_rule"] == "minimum_data_through_date_across_participating_sources"
    assert time["comparison_requires_trimmable_coverage"] is True
    assert time["preserve_native_freshness"] is True
    assert time["numeric_freshness_thresholds"] == "none_until_source_cadence_is_reviewed"
    assert set(time["required"]) == {
        "snapshot_date", "data_through_date", "period_start", "period_end", "period_type", "import_batch_id"
    }


def test_phase2a_acceptance_stays_within_vertical_slice_boundary():
    contract_text = CONTRACT.read_text(encoding="utf-8")
    checkpoint_text = CHECKPOINT.read_text(encoding="utf-8")
    assert "green/yellow/red threshold is invented" in contract_text.lower()
    assert "PHASE_2A_ACCEPTANCE = ACCEPTED" in checkpoint_text
    assert "This work directly supports the STORM cockpit and does not expand STORM into a general-purpose finance/data warehouse." in checkpoint_text
    assert "no Feishu write and no schema change" in checkpoint_text
    assert "No Structured Metrics table was added" in checkpoint_text
