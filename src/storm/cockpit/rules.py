"""Approved deterministic Business Health Rules v1 for Phase 2C."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .models import (
    AvailabilityState,
    BusinessHealthSnapshot,
    BusinessHealthState,
    DataConfidenceState,
    DataStatus,
    DerivedMetric,
    FreshnessState,
    MetricFact,
    RuleEvaluation,
)


RULE_VERSION = "BUSINESS_HEALTH_RULES_V1"


def _value(metric: MetricFact | DerivedMetric) -> Any:
    return metric.value


def _ready(metric: MetricFact) -> bool:
    return (
        metric.availability == AvailabilityState.AVAILABLE
        and metric.freshness not in {
            FreshnessState.STALE,
            FreshnessState.SOURCE_NOT_AVAILABLE,
        }
        and metric.value is not None
    )


def _same_month(actual: MetricFact, target: MetricFact) -> bool:
    if not actual.period_start or not actual.period_end or not target.period_start or not target.period_end:
        return False
    month = target.period_start[:7]
    return (
        target.period_type == "MONTHLY_TARGET"
        and target.period_end[:7] == month
        and actual.period_start[:7] == month
        and actual.period_end[:7] == month
        and actual.period_end <= target.period_end
    )


def _lineage(*metrics: MetricFact) -> tuple[str, ...]:
    entries: list[str] = []
    for metric in metrics:
        entries.append(
            "|".join(
                filter(
                    None,
                    (
                        metric.metric_name,
                        metric.source_system,
                        metric.source_artifact,
                        metric.source_release,
                        metric.import_batch_id,
                        metric.data_through_date,
                    ),
                )
            )
        )
    return tuple(entries)


def _evaluation(
    rule_id: str,
    result: str,
    eligible: bool,
    inputs: Mapping[str, Any],
    formula_or_rule: str,
    reason: str,
    lineage: tuple[str, ...],
    notes: tuple[str, ...] = (),
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        result=result,
        eligible=eligible,
        input_metrics=dict(inputs),
        formula_or_rule=formula_or_rule,
        reason=reason,
        lineage=lineage,
        notes=notes,
    )


def evaluate_sales_health(
    facts: Mapping[str, MetricFact],
    derived: Mapping[str, DerivedMetric],
    data_status: Mapping[str, DataStatus],
) -> RuleEvaluation:
    actual = facts["actual_sales"]
    target = facts["bp_sales"]
    attainment = derived["sales_attainment_pct"]
    trend = derived["weekly_sales_change"]
    eligible = (
        _ready(actual)
        and _ready(target)
        and _same_month(actual, target)
        and actual.source_release is not None
        and data_status["sales"].availability == AvailabilityState.AVAILABLE
    )
    inputs = {
        "actual_sales": _value(actual),
        "bp_sales": _value(target),
        "sales_attainment_pct": _value(attainment),
        "weekly_sales_change_pct": (
            trend.value.get("percent_change") if isinstance(trend.value, Mapping) else None
        ),
    }
    formula = (
        "UNKNOWN if ineligible; RED if actual_sales < 0; else GREEN if attainment >= 0.95; "
        "YELLOW if attainment >= 0.80; else RED; then downgrade one level only when a valid "
        "consecutive equal-length WEEKLY_OPERATING change <= -0.25"
    )
    if not eligible or attainment.availability != AvailabilityState.AVAILABLE:
        return _evaluation(
            "sales_health", BusinessHealthState.UNKNOWN, False, inputs, formula,
            "Authoritative Actual Sales and compatible BP Sales evidence is incomplete or incompatible.",
            _lineage(actual, target),
        )
    if float(actual.value) < 0:
        return _evaluation(
            "sales_health", BusinessHealthState.RED, True, inputs, formula,
            f"Actual Sales is negative ({float(actual.value):.2f} < 0).",
            _lineage(actual, target),
        )
    ratio = float(attainment.value)
    if ratio >= 0.95:
        result = BusinessHealthState.GREEN
        reason = f"Sales attainment {ratio:.6f} is at or above 0.95."
    elif ratio >= 0.80:
        result = BusinessHealthState.YELLOW
        reason = f"Sales attainment {ratio:.6f} is at or above 0.80 and below 0.95."
    else:
        result = BusinessHealthState.RED
        reason = f"Sales attainment {ratio:.6f} is below 0.80."

    trend_status = data_status.get("weekly_trend")
    valid_trend = (
        trend.availability == AvailabilityState.AVAILABLE
        and isinstance(trend.value, Mapping)
        and trend.value.get("percent_change") is not None
        and trend_status is not None
        and trend_status.period_type == "WEEKLY_OPERATING"
        and trend_status.availability == AvailabilityState.AVAILABLE
    )
    if valid_trend and float(trend.value["percent_change"]) <= -0.25:
        downgraded = {
            BusinessHealthState.GREEN: BusinessHealthState.YELLOW,
            BusinessHealthState.YELLOW: BusinessHealthState.RED,
            BusinessHealthState.RED: BusinessHealthState.RED,
        }[result]
        if downgraded != result:
            reason += (
                f" Valid weekly change {float(trend.value['percent_change']):.6f} is <= -0.25, "
                f"so {result.value} is downgraded to {downgraded.value}."
            )
        result = downgraded
    return _evaluation(
        "sales_health", result, True, inputs, formula, reason, _lineage(actual, target),
        ("Positive weekly change never upgrades Sales Health.",),
    )


def evaluate_cm_health(
    facts: Mapping[str, MetricFact],
    derived: Mapping[str, DerivedMetric],
    data_status: Mapping[str, DataStatus],
) -> RuleEvaluation:
    actual = facts["actual_cm"]
    target = facts["bp_cm"]
    basis_sales = facts["cm_basis_sales"]
    attainment = derived["cm_attainment_pct"]
    cm_pct = derived["actual_cm_pct"]
    reconciled = (
        actual.import_batch_id is not None
        and actual.import_batch_id == target.import_batch_id == basis_sales.import_batch_id
        and data_status["cm_actual"].availability == AvailabilityState.AVAILABLE
        and data_status["bp_plan"].availability == AvailabilityState.AVAILABLE
    )
    eligible = _ready(actual) and _ready(target) and _same_month(actual, target) and reconciled
    inputs = {
        "actual_cm": _value(actual),
        "bp_cm": _value(target),
        "cm_attainment_pct": _value(attainment),
        "actual_cm_pct": _value(cm_pct),
        "reconciled_same_batch": reconciled,
    }
    formula = (
        "UNKNOWN if ineligible; RED if actual_cm < 0; RED if cm_pct < 0; "
        "else GREEN if attainment >= 0.95; YELLOW if attainment >= 0.80; else RED"
    )
    if not eligible or attainment.availability != AvailabilityState.AVAILABLE:
        return _evaluation(
            "cm_health", BusinessHealthState.UNKNOWN, False, inputs, formula,
            "Authoritative, period-compatible and reconciled Actual CM/BP CM evidence is incomplete.",
            _lineage(actual, target, basis_sales),
        )
    if float(actual.value) < 0:
        result = BusinessHealthState.RED
        reason = f"Actual CM is negative ({float(actual.value):.2f} < 0)."
    elif cm_pct.value is not None and float(cm_pct.value) < 0:
        result = BusinessHealthState.RED
        reason = f"CM% is negative ({float(cm_pct.value):.6f} < 0)."
    else:
        ratio = float(attainment.value)
        if ratio >= 0.95:
            result = BusinessHealthState.GREEN
            reason = f"CM attainment {ratio:.6f} is at or above 0.95."
        elif ratio >= 0.80:
            result = BusinessHealthState.YELLOW
            reason = f"CM attainment {ratio:.6f} is at or above 0.80 and below 0.95."
        else:
            result = BusinessHealthState.RED
            reason = f"CM attainment {ratio:.6f} is below 0.80."
    return _evaluation(
        "cm_health", result, True, inputs, formula, reason,
        _lineage(actual, target, basis_sales),
        ("THD Main/DFC logic is not executed for WALMART_MP.",),
    )


def evaluate_advertising_health(facts: Mapping[str, MetricFact]) -> RuleEvaluation:
    spend = facts["ad_spend"]
    sales = facts["attributed_ad_sales"]
    available = _ready(spend) and _ready(sales)
    inputs = {"ad_spend": _value(spend), "attributed_ad_sales": _value(sales)}
    formula = "RED only when ad_spend > 0 and attributed_ad_sales == 0; otherwise UNKNOWN"
    if not available:
        result = BusinessHealthState.UNKNOWN
        reason = "Advertising spend or attributed-sales evidence is unavailable."
    elif float(spend.value) > 0 and float(sales.value) == 0:
        result = BusinessHealthState.RED
        reason = "Ad Spend is positive while Attributed Sales equals zero."
    else:
        result = BusinessHealthState.UNKNOWN
        reason = "No approved GREEN/YELLOW ROAS rule applies to the available advertising facts."
    return _evaluation(
        "advertising_health", result, available, inputs, formula, reason,
        _lineage(spend, sales),
    )


def evaluate_inventory_health(facts: Mapping[str, MetricFact]) -> RuleEvaluation:
    inventory = facts["inventory_condition"]
    return _evaluation(
        "inventory_health", BusinessHealthState.UNKNOWN, False,
        {"inventory_units": facts["inventory_units"].value, "inventory_condition": inventory.value},
        "UNKNOWN in Phase 2C; raw OOS counts are not an approved materiality rule",
        "No already-approved deterministic Walmart inventory threshold is applicable.",
        _lineage(facts["inventory_units"], inventory),
    )


def evaluate_data_confidence(
    data_status: Mapping[str, DataStatus],
    warnings: tuple[str, ...],
) -> RuleEvaluation:
    required = ("sales", "cm_actual", "bp_plan")
    inputs = {
        key: {
            "availability": data_status[key].availability.value,
            "freshness": data_status[key].freshness.value,
            "data_through_date": data_status[key].data_through_date,
        }
        for key in required
        if key in data_status
    }
    formula = (
        "LOW for stale/unavailable/invalid core evidence; MEDIUM for trustworthy core evidence with "
        "non-blocking lag, cutoff mismatch, optional-source gap or warning; HIGH when core evidence is "
        "current and no limitation exists; otherwise UNKNOWN"
    )
    if any(key not in data_status for key in required):
        return _evaluation(
            "data_confidence", DataConfidenceState.UNKNOWN, False, inputs, formula,
            "Required confidence evidence is missing.", (),
        )
    blocking_warning_tokens = (
        "RECONCILIATION_FAILURE",
        "UNRESOLVED_SEMANTIC_CONFLICT",
        "INVALID_OFFICIAL_RELEASE",
        "FAILED_PROTECTED",
    )
    core_failure = any(
        data_status[key].availability != AvailabilityState.AVAILABLE
        or data_status[key].freshness in {
            FreshnessState.STALE,
            FreshnessState.SOURCE_NOT_AVAILABLE,
        }
        for key in required
    ) or any(token in warning for token in blocking_warning_tokens for warning in warnings)
    lineage = tuple(item for key in required for item in data_status[key].lineage)
    if core_failure:
        return _evaluation(
            "data_confidence", DataConfidenceState.LOW, True, inputs, formula,
            "At least one core source is stale, unavailable, unreconciled, semantically unresolved or invalid.",
            lineage,
        )
    non_blocking_limitations: list[str] = []
    if any(data_status[key].freshness == FreshnessState.LAGGING for key in required):
        non_blocking_limitations.append("known core-source lag")
    cross = data_status.get("cross_domain_comparison")
    if cross and cross.availability == AvailabilityState.NOT_COMPARABLE:
        non_blocking_limitations.append("source cutoff mismatch")
    ytd = data_status.get("ytd_cm")
    if ytd and ytd.availability == AvailabilityState.SOURCE_NOT_AVAILABLE:
        non_blocking_limitations.append("optional YTD CM unavailable")
    supporting = ("advertising", "inventory", "weekly_trend")
    if any(
        key in data_status
        and (
            data_status[key].freshness in {FreshnessState.LAGGING, FreshnessState.STALE}
            or data_status[key].availability in {
                AvailabilityState.SOURCE_NOT_AVAILABLE,
                AvailabilityState.NOT_COMPARABLE,
                AvailabilityState.UNRESOLVED,
            }
        )
        for key in supporting
    ):
        non_blocking_limitations.append("supporting-domain limitation")
    if warnings:
        non_blocking_limitations.append("non-blocking source warning")
    if non_blocking_limitations:
        return _evaluation(
            "data_confidence", DataConfidenceState.MEDIUM, True, inputs, formula,
            "Core Sales and CM evidence is trustworthy; " + ", ".join(dict.fromkeys(non_blocking_limitations)) + ".",
            lineage,
        )
    return _evaluation(
        "data_confidence", DataConfidenceState.HIGH, True, inputs, formula,
        "Core Sales and CM evidence is authoritative, reconciled, current and free of blocking or non-blocking limitations.",
        lineage,
    )


def evaluate_overall_health(sales: RuleEvaluation, cm: RuleEvaluation) -> RuleEvaluation:
    inputs = {"sales_health": sales.result, "cm_health": cm.result}
    formula = (
        "RED if Sales or CM is RED; else YELLOW if either is YELLOW; "
        "else GREEN if both are GREEN; otherwise UNKNOWN"
    )
    if BusinessHealthState.RED in {sales.result, cm.result}:
        result = BusinessHealthState.RED
    elif BusinessHealthState.YELLOW in {sales.result, cm.result}:
        result = BusinessHealthState.YELLOW
    elif sales.result == cm.result == BusinessHealthState.GREEN:
        result = BusinessHealthState.GREEN
    else:
        result = BusinessHealthState.UNKNOWN
    return _evaluation(
        "overall_health", result, sales.eligible and cm.eligible, inputs, formula,
        f"Overall Health follows Sales={sales.result} and CM={cm.result} precedence; Ads and Inventory do not override v1.",
        sales.lineage + cm.lineage,
    )


def activate_rules_v1(snapshot: BusinessHealthSnapshot) -> BusinessHealthSnapshot:
    """Return a new snapshot with approved v1 rules; never persists or writes externally."""

    sales = evaluate_sales_health(snapshot.facts, snapshot.derived_control_metrics, snapshot.data_status)
    cm = evaluate_cm_health(snapshot.facts, snapshot.derived_control_metrics, snapshot.data_status)
    advertising = evaluate_advertising_health(snapshot.facts)
    inventory = evaluate_inventory_health(snapshot.facts)
    confidence = evaluate_data_confidence(snapshot.data_status, snapshot.warnings)
    overall = evaluate_overall_health(sales, cm)
    evaluations = {
        item.rule_id: item
        for item in (sales, cm, advertising, inventory, confidence, overall)
    }
    primary_driver = "UNRESOLVED"
    if sales.result == BusinessHealthState.RED:
        primary_driver = f"Sales Health RED — {sales.reason}"
    elif cm.result == BusinessHealthState.RED:
        primary_driver = f"CM Health RED — {cm.reason}"
    interpretation = {
        "overall_status": overall.result,
        "sales_status": sales.result,
        "cm_status": cm.result,
        "ads_status": advertising.result,
        "inventory_status": inventory.result,
        "data_confidence": confidence.result,
        "primary_driver": primary_driver,
        "key_risk": "UNRESOLVED",
        "key_opportunity": "UNRESOLVED",
        "required_action": "UNRESOLVED",
    }
    warnings = tuple(
        warning for warning in snapshot.warnings if not warning.startswith("NO_HEALTH_THRESHOLDS:")
    ) + ("BUSINESS_HEALTH_RULES_V1_ACTIVE.",)
    return replace(
        snapshot,
        schema_version=3,
        rule_evaluations=evaluations,
        interpretation=interpretation,
        warnings=warnings,
    )
