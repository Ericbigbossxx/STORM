"""Platform-neutral value objects for the Phase 2A Business Health slice."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any, Mapping


class FreshnessState(StrEnum):
    CURRENT = "CURRENT"
    LAGGING = "LAGGING"
    STALE = "STALE"
    SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AvailabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNRESOLVED = "UNRESOLVED"


class BusinessHealthState(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class DataConfidenceState(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MetricFact:
    metric_name: str
    value: Any
    unit: str
    period_type: str
    period_start: str | None
    period_end: str | None
    snapshot_date: str | None
    data_through_date: str | None
    availability: AvailabilityState
    freshness: FreshnessState
    source_system: str
    source_artifact: str | None
    source_release: str | None
    import_batch_id: str | None
    source_generated_at: str | None = None
    source_timezone: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DataStatus:
    domain: str
    source_system: str
    source_artifact: str | None
    source_release: str | None
    snapshot_date: str | None
    data_through_date: str | None
    period_start: str | None
    period_end: str | None
    period_type: str
    freshness: FreshnessState
    availability: AvailabilityState
    lineage: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DerivedMetric:
    metric_name: str
    value: Any
    unit: str
    availability: AvailabilityState
    formula: str | None
    inputs: tuple[str, ...]
    comparison_through_date: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    rule_id: str
    rule_version: str
    result: str
    eligible: bool
    input_metrics: Mapping[str, Any]
    formula_or_rule: str
    reason: str
    lineage: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BusinessHealthSnapshot:
    schema_version: int
    control_week: str
    market: str
    platform: str
    level: str
    snapshot_date: str
    facts: Mapping[str, MetricFact]
    data_status: Mapping[str, DataStatus]
    derived_control_metrics: Mapping[str, DerivedMetric]
    interpretation: Mapping[str, str]
    rule_evaluations: Mapping[str, RuleEvaluation] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(self)


def _to_plain(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: _to_plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value
