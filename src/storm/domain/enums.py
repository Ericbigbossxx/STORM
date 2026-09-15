"""Stable cross-platform status semantics for STORM v0.1."""

from enum import StrEnum


class Health(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class HealthLevel(StrEnum):
    PLATFORM = "PLATFORM"
    CHANNEL = "CHANNEL"


class DataCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MINIMAL = "MINIMAL"
    UNKNOWN = "UNKNOWN"


class SourceType(StrEnum):
    MANUAL = "MANUAL"
    EXPORT = "EXPORT"
    SYSTEM = "SYSTEM"
    AGENT = "AGENT"
    MIXED = "MIXED"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Buyability(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class ListingStatus(StrEnum):
    HEALTHY = "HEALTHY"
    ISSUE = "ISSUE"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class ActionStatus(StrEnum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    EXECUTED_WAITING_VALIDATION = "EXECUTED_WAITING_VALIDATION"
    VALIDATED_EFFECTIVE = "VALIDATED_EFFECTIVE"
    VALIDATED_INEFFECTIVE = "VALIDATED_INEFFECTIVE"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class SignalType(StrEnum):
    ISSUE = "ISSUE"
    RISK = "RISK"
    OPPORTUNITY = "OPPORTUNITY"


class SignalStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SignalCategory(StrEnum):
    SALES = "SALES"
    TRAFFIC = "TRAFFIC"
    CONVERSION = "CONVERSION"
    ADS = "ADS"
    INVENTORY = "INVENTORY"
    BUYABILITY = "BUYABILITY"
    LISTING = "LISTING"
    FULFILLMENT = "FULFILLMENT"
    REVIEW = "REVIEW"
    ACCOUNT = "ACCOUNT"
    PROMOTION = "PROMOTION"
    ONBOARDING = "ONBOARDING"
    SYSTEM = "SYSTEM"
    OTHER = "OTHER"


class SkuRole(StrEnum):
    HERO = "HERO"
    GROWTH = "GROWTH"
    PROFIT = "PROFIT"
    TRAFFIC = "TRAFFIC"
    CLEARANCE = "CLEARANCE"
    NEW = "NEW"
    WATCH = "WATCH"
    OTHER = "OTHER"
