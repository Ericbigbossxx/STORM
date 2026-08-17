"""Typed Phase 1 data contract for STORM V2.

The module intentionally models nullable facts explicitly.  Unknown values are
``None`` in Python and render as ``UNKNOWN`` in audit output; no defaulting or
zero-filling is permitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Mapping


CANONICAL_HIERARCHY = (
    "Platform",
    "Channel/Subchannel",
    "Brand",
    "Power Source",
    "SKU",
)


class MetricDomain(StrEnum):
    SALES = "SALES"
    ADS = "ADS"
    CM_BUSINESS_PERFORMANCE = "CM_BUSINESS_PERFORMANCE"
    THD_DFC_SELLOUT = "THD_DFC_SELLOUT"


class MappingStatus(StrEnum):
    MAPPED = "MAPPED"
    UNMAPPED = "UNMAPPED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DataQualityStatus(StrEnum):
    VALID = "VALID"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    source_file: str
    byte_size: int
    sha256: str
    captured_at: datetime
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class SourceSection:
    sheet: str
    section_label: str
    header_sequence: tuple[str | None, ...]
    header_row: int | None
    cell_range: str
    record_count: int


@dataclass(frozen=True, slots=True)
class CanonicalMetricRecord:
    metric_domain: MetricDomain
    metric_name: str
    metric_value: float | int | None
    metric_unit: str
    scenario: str
    period_date: date | None
    platform: str | None
    channel_subchannel: str | None
    brand: str | None
    power_source: str | None
    sku: str | None
    mapping_status: MappingStatus
    source_file: str
    source_sha256: str
    source_sheet: str
    source_section: str
    source_header: str
    source_reference: str
    raw_value: Any
    raw_dimensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        trace = (
            self.source_file,
            self.source_sha256,
            self.source_sheet,
            self.source_section,
            self.source_header,
            self.source_reference,
        )
        if not all(trace):
            raise ValueError("Canonical records require complete source traceability")


@dataclass(frozen=True, slots=True)
class MappingResult:
    raw_value: Any
    normalized_value: str | None
    canonical_value: str | None
    status: MappingStatus
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    status: DataQualityStatus
    sheet: str
    source_reference: str
    summary: str
    affected_records: int
    blocking: bool = False

    def __post_init__(self) -> None:
        if self.blocking != (self.status is DataQualityStatus.BLOCKING):
            raise ValueError("blocking flag must agree with quality status")
