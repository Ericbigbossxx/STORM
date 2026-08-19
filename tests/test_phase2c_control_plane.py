from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from storm.cockpit.feishu_dry_run import build_feishu_write_candidate, render_preview_v3
from storm.cockpit.models import (
    AvailabilityState,
    BusinessHealthSnapshot,
    DataStatus,
    DerivedMetric,
    FreshnessState,
    MetricFact,
)
from storm.cockpit.rules import (
    activate_rules_v1,
    evaluate_advertising_health,
    evaluate_cm_health,
    evaluate_data_confidence,
    evaluate_inventory_health,
    evaluate_overall_health,
    evaluate_sales_health,
)


ROOT = Path(__file__).parents[1]


def _fact(
    name: str,
    value: object,
    *,
    period_type: str = "MTD_OPERATING",
    period_start: str = "2026-08-01",
    period_end: str = "2026-08-02",
    availability: AvailabilityState = AvailabilityState.AVAILABLE,
    freshness: FreshnessState = FreshnessState.CURRENT,
    source_system: str = "AUTHORITATIVE",
    source_release: str = "RELEASE-1",
    batch: str | None = "BATCH-1",
) -> MetricFact:
    return MetricFact(
        metric_name=name,
        value=value,
        unit="USD",
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        snapshot_date="2026-08-11",
        data_through_date=period_end,
        availability=availability,
        freshness=freshness,
        source_system=source_system,
        source_artifact=f"{name}.parquet",
        source_release=source_release,
        import_batch_id=batch,
    )


def _status(
    domain: str,
    *,
    availability: AvailabilityState = AvailabilityState.AVAILABLE,
    freshness: FreshnessState = FreshnessState.CURRENT,
    period_type: str = "MTD_OPERATING",
) -> DataStatus:
    return DataStatus(
        domain=domain,
        source_system="AUTHORITATIVE",
        source_artifact=f"{domain}.parquet",
        source_release="RELEASE-1",
        snapshot_date="2026-08-11",
        data_through_date="2026-08-02",
        period_start="2026-08-01",
        period_end="2026-08-02",
        period_type=period_type,
        freshness=freshness,
        availability=availability,
        lineage=(f"{domain}-lineage",),
    )


def _facts(*, actual_sales: float = 100.0, actual_cm: float = 100.0,
           ad_spend: float | None = 10.0, ad_sales: float | None = 20.0) -> dict[str, MetricFact]:
    return {
        "actual_sales": _fact("actual_sales", actual_sales),
        "bp_sales": _fact("bp_sales", 100.0, period_type="MONTHLY_TARGET", period_end="2026-08-31"),
        "actual_cm": _fact("actual_cm", actual_cm, period_type="MTD", period_end="2026-08-10"),
        "bp_cm": _fact("bp_cm", 100.0, period_type="MONTHLY_TARGET", period_end="2026-08-31"),
        "cm_basis_sales": _fact("cm_basis_sales", 200.0, period_type="MTD", period_end="2026-08-10"),
        "ad_spend": _fact("ad_spend", ad_spend, availability=AvailabilityState.AVAILABLE if ad_spend is not None else AvailabilityState.SOURCE_NOT_AVAILABLE),
        "attributed_ad_sales": _fact("attributed_ad_sales", ad_sales, availability=AvailabilityState.AVAILABLE if ad_sales is not None else AvailabilityState.SOURCE_NOT_AVAILABLE),
        "roas": _fact("roas", None if not ad_spend else (ad_sales or 0) / ad_spend),
        "inventory_units": _fact("inventory_units", 12),
        "inventory_condition": _fact("inventory_condition", {"In Stock": 2, "Out of Stock": 1}),
        "ytd_actual_cm": _fact("ytd_actual_cm", None, availability=AvailabilityState.SOURCE_NOT_AVAILABLE, freshness=FreshnessState.SOURCE_NOT_AVAILABLE),
    }


def _derived(
    *,
    sales_attainment: float = 1.0,
    cm_attainment: float = 1.0,
    cm_pct: float = 0.5,
    weekly_change: float | None = None,
    weekly_availability: AvailabilityState = AvailabilityState.AVAILABLE,
) -> dict[str, DerivedMetric]:
    trend_value = None if weekly_change is None else {
        "percent_change": weekly_change,
        "absolute_change": weekly_change * 100,
        "previous_period_start": "2026-07-20",
        "previous_period_end": "2026-07-26",
        "current_period_start": "2026-07-27",
        "current_period_end": "2026-08-02",
        "coverage_days": 7,
    }
    return {
        "sales_attainment_pct": DerivedMetric("sales_attainment_pct", sales_attainment, "RATIO", AvailabilityState.AVAILABLE, "actual/bp", ("actual_sales", "bp_sales")),
        "cm_attainment_pct": DerivedMetric("cm_attainment_pct", cm_attainment, "RATIO", AvailabilityState.AVAILABLE, "actual/bp", ("actual_cm", "bp_cm")),
        "actual_cm_pct": DerivedMetric("actual_cm_pct", cm_pct, "RATIO", AvailabilityState.AVAILABLE, "cm/sales", ("actual_cm", "cm_basis_sales")),
        "weekly_sales_change": DerivedMetric("weekly_sales_change", trend_value, "RATIO", weekly_availability, "weekly", ("prior", "current")),
        "sales_cm_common_cutoff_metric": DerivedMetric("sales_cm_common_cutoff_metric", None, "NA", AvailabilityState.NOT_COMPARABLE, None, ("sales", "cm")),
    }


def _statuses() -> dict[str, DataStatus]:
    return {
        "sales": _status("sales"),
        "cm_actual": _status("cm_actual", period_type="MTD"),
        "bp_plan": _status("bp_plan", period_type="MONTHLY_TARGET"),
        "advertising": _status("advertising"),
        "inventory": _status("inventory", availability=AvailabilityState.UNRESOLVED, period_type="SNAPSHOT"),
        "weekly_trend": _status("weekly_trend", period_type="WEEKLY_OPERATING"),
        "ytd_cm": _status("ytd_cm", availability=AvailabilityState.SOURCE_NOT_AVAILABLE, freshness=FreshnessState.SOURCE_NOT_AVAILABLE, period_type="YTD"),
        "cross_domain_comparison": _status("cross_domain_comparison", availability=AvailabilityState.NOT_COMPARABLE, freshness=FreshnessState.NOT_APPLICABLE, period_type="NATIVE_SOURCE_PERIODS"),
    }


def _snapshot(*, actual_sales: float = -694.21, actual_cm: float = -5.0,
              ad_spend: float = 10.0, ad_sales: float = 0.0) -> BusinessHealthSnapshot:
    return BusinessHealthSnapshot(
        schema_version=2,
        control_week="2026-W33",
        market="US",
        platform="WALMART_MP",
        level="PLATFORM",
        snapshot_date="2026-08-11",
        facts=_facts(actual_sales=actual_sales, actual_cm=actual_cm, ad_spend=ad_spend, ad_sales=ad_sales),
        data_status=_statuses(),
        derived_control_metrics=_derived(sales_attainment=actual_sales / 100, cm_attainment=actual_cm / 100, cm_pct=actual_cm / 200, weekly_change=-0.30),
        interpretation={"overall_status": "UNRESOLVED"},
        warnings=("MIXED_NATIVE_CUTOFFS", "YTD_CM_SOURCE_NOT_AVAILABLE"),
    )


def test_active_rules_contract_is_deterministic_and_write_gated() -> None:
    contract = yaml.safe_load((ROOT / "config" / "business_health_rules_v1.yaml").read_text(encoding="utf-8"))
    assert contract["status"] == "ACTIVE_APPROVED_PHASE_2C"
    assert contract["active"] is True
    assert contract["implementation"] == "deterministic_only"
    assert contract["llm_judgment_allowed"] is False
    assert contract["external_record_write_allowed"] is False


def test_sales_negative_actual_is_hard_red() -> None:
    result = evaluate_sales_health(_facts(actual_sales=-1), _derived(sales_attainment=-0.01), _statuses())
    assert result.result == "RED"
    assert "negative" in result.reason


@pytest.mark.parametrize(("attainment", "expected"), [(0.95, "GREEN"), (0.80, "YELLOW"), (0.79, "RED")])
def test_sales_attainment_bands(attainment: float, expected: str) -> None:
    result = evaluate_sales_health(_facts(), _derived(sales_attainment=attainment), _statuses())
    assert result.result == expected


def test_weekly_trend_can_only_downgrade_and_positive_cannot_upgrade() -> None:
    downgraded = evaluate_sales_health(_facts(), _derived(sales_attainment=0.95, weekly_change=-0.25), _statuses())
    positive = evaluate_sales_health(_facts(), _derived(sales_attainment=0.80, weekly_change=0.50), _statuses())
    assert downgraded.result == "YELLOW"
    assert positive.result == "YELLOW"


def test_invalid_weekly_period_cannot_affect_sales_health() -> None:
    statuses = _statuses()
    statuses["weekly_trend"] = _status("weekly_trend", availability=AvailabilityState.NOT_COMPARABLE, period_type="MTD_OPERATING")
    result = evaluate_sales_health(_facts(), _derived(sales_attainment=0.95, weekly_change=-0.50), statuses)
    assert result.result == "GREEN"


def test_cm_negative_is_hard_red_and_attainment_bands_apply() -> None:
    negative = evaluate_cm_health(_facts(actual_cm=-1), _derived(cm_attainment=-0.01, cm_pct=-0.01), _statuses())
    green = evaluate_cm_health(_facts(), _derived(cm_attainment=0.95), _statuses())
    yellow = evaluate_cm_health(_facts(), _derived(cm_attainment=0.80), _statuses())
    red = evaluate_cm_health(_facts(), _derived(cm_attainment=0.79), _statuses())
    assert (negative.result, green.result, yellow.result, red.result) == ("RED", "GREEN", "YELLOW", "RED")


def test_ads_hard_rule_and_no_unapproved_target() -> None:
    assert evaluate_advertising_health(_facts(ad_spend=10, ad_sales=0)).result == "RED"
    assert evaluate_advertising_health(_facts(ad_spend=10, ad_sales=20)).result == "UNKNOWN"
    assert evaluate_advertising_health(_facts(ad_spend=None, ad_sales=None)).result == "UNKNOWN"


def test_inventory_remains_unknown() -> None:
    assert evaluate_inventory_health(_facts()).result == "UNKNOWN"


def test_data_confidence_high_medium_low() -> None:
    high_status = {key: value for key, value in _statuses().items() if key in {"sales", "cm_actual", "bp_plan"}}
    high = evaluate_data_confidence(high_status, ())
    medium = evaluate_data_confidence(_statuses(), ("NON_BLOCKING_WARNING",))
    low_status = _statuses()
    low_status["sales"] = _status("sales", freshness=FreshnessState.STALE)
    low = evaluate_data_confidence(low_status, ())
    assert (high.result, medium.result, low.result) == ("HIGH", "MEDIUM", "LOW")


def test_data_confidence_does_not_override_business_health_and_overall_precedence() -> None:
    activated = activate_rules_v1(_snapshot())
    assert activated.interpretation["data_confidence"] == "MEDIUM"
    assert activated.interpretation["overall_status"] == "RED"
    overall = evaluate_overall_health(
        replace(activated.rule_evaluations["sales_health"], result="GREEN"),
        replace(activated.rule_evaluations["cm_health"], result="YELLOW"),
    )
    assert overall.result == "YELLOW"


def test_feishu_cm_confidence_mapping_and_live_candidate_write_gate() -> None:
    snapshot = activate_rules_v1(_snapshot())
    candidate = build_feishu_write_candidate(snapshot, ROOT / "config" / "feishu_schema.yaml")
    assert candidate.identity["record_identity"] == "HLT-2026W33-US-WMT"
    assert candidate.create_fields["CM Health"] == "RED"
    assert candidate.create_fields["Data Confidence"] == "MEDIUM"
    assert candidate.create_fields["Overall Health"] == "RED"
    assert candidate.validation["only_approved_schema_delta"] is True
    assert candidate.validation["deployment_status"] == "ACTIVE_CANONICAL"
    assert candidate.target["table_id"] == "tblrYMjU0V7eMo8F"
    assert candidate.target["field_ids"]["CM Health"] == "fldNSdSCqu"
    assert candidate.target["field_ids"]["Data Confidence"] == "fldj9HwTg5"
    assert candidate.validation["record_api_invoked"] is False
    assert candidate.validation["external_record_write_performed"] is False
    assert candidate.mode == "LIVE_WRITE_CANDIDATE_ONLY"
    preview = render_preview_v3(snapshot, candidate)
    assert "Overall Health:** `RED`" in preview
    assert "Record API invoked: `false`" in preview


def test_phase2c_builder_has_no_record_write_api_path() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "scripts" / "build_phase2c_walmart_control_plane.py",
            ROOT / "src" / "storm" / "cockpit" / "feishu_dry_run.py",
            ROOT / "src" / "storm" / "cockpit" / "rules.py",
        )
    )
    assert "bitable_v1_appTableRecord_create" not in sources
    assert "bitable_v1_appTableRecord_update" not in sources
