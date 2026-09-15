"""Small, platform-neutral domain value objects for adapter boundaries."""

from dataclasses import dataclass, field
from datetime import date, datetime

from .enums import Confidence, HealthLevel, SourceType


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


@dataclass(frozen=True, slots=True)
class CanonicalDimensions:
    """Management identity; values are validated against dimensions.yaml by services."""

    market: str
    platform: str
    channel: str | None = None
    product_line: str | None = None
    sku: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", _required_text(self.market, "market"))
        object.__setattr__(self, "platform", _required_text(self.platform, "platform"))


@dataclass(frozen=True, slots=True)
class BusinessHealthKey:
    """The only active Business Health key in v0.1."""

    week_id: str
    market: str
    platform: str
    level: HealthLevel = HealthLevel.PLATFORM
    channel: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "week_id", _required_text(self.week_id, "week_id"))
        object.__setattr__(self, "market", _required_text(self.market, "market"))
        object.__setattr__(self, "platform", _required_text(self.platform, "platform"))
        if self.level is not HealthLevel.PLATFORM:
            raise ValueError("CHANNEL Business Health rows are reserved and inactive in v0.1")
        if self.channel is not None:
            raise ValueError("channel must be blank for PLATFORM Business Health rows")


@dataclass(frozen=True, slots=True)
class Provenance:
    data_as_of: date | None
    source_type: SourceType
    source_ref: str | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AdvisoryAssessment:
    """AI output that cannot become a final business decision by itself."""

    ai_analysis: str | None = None
    ai_suggested_status: str | None = None
    ai_confidence: Confidence | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class HumanDecision:
    decision: str | None
    reviewed: bool = False
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.reviewed and not self.decision:
            raise ValueError("a reviewed decision must include the human decision")
        if self.reviewed and self.reviewed_at is None:
            raise ValueError("a reviewed decision must include reviewed_at")
